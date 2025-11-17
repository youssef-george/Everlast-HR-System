from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_from_directory
from flask_login import login_required, current_user
from forms import DocumentationPageForm, DeleteForm
from models import db, DocumentationPage, User
from helpers import role_required
from sqlalchemy import or_, func
import os
import logging
from werkzeug.utils import secure_filename
from datetime import datetime

logger = logging.getLogger(__name__)

documentation_bp = Blueprint('documentation', __name__, url_prefix='/documentation')

# Allowed file extensions for image uploads
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@documentation_bp.route('/')
@login_required
def index():
    """Public-facing documentation page with search and filters"""
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '')
    tag_filter = request.args.get('tag', '')
    sort_by = request.args.get('sort', 'recent')  # recent, popular, alphabetical
    
    # Base query - only published pages visible to user's role
    query = DocumentationPage.query.filter_by(is_published=True)
    
    # Filter by visibility - Product Owner sees everything
    if current_user.role != 'product_owner':
        # Filter pages visible to user's role
        # Check if the user's role is in the visible_roles array
        # Using PostgreSQL array overlap operator (&&) to check if arrays have common elements
        from sqlalchemy import text
        query = query.filter(
            DocumentationPage.visible_roles.isnot(None)
        ).filter(
            text(f"'{current_user.role}' = ANY(visible_roles)")
        )
    
    # Apply search filter
    if search_query:
        search_pattern = f'%{search_query}%'
        from sqlalchemy import text
        query = query.filter(
            or_(
                DocumentationPage.title.ilike(search_pattern),
                DocumentationPage.content.ilike(search_pattern),
                text(f"'{search_query}' = ANY(tags)")
            )
        )
    
    # Apply category filter
    if category_filter:
        query = query.filter_by(category=category_filter)
    
    # Apply tag filter
    if tag_filter:
        from sqlalchemy import text
        query = query.filter(text(f"'{tag_filter}' = ANY(tags)"))
    
    # Apply sorting
    if sort_by == 'popular':
        query = query.order_by(DocumentationPage.view_count.desc())
    elif sort_by == 'alphabetical':
        query = query.order_by(DocumentationPage.title.asc())
    else:  # recent
        query = query.order_by(DocumentationPage.created_at.desc())
    
    pages = query.all()
    
    # Get all categories for filter dropdown
    categories = db.session.query(DocumentationPage.category).distinct().all()
    categories = [cat[0] for cat in categories if cat[0]]
    
    # Get all tags for filter
    all_tags = []
    for page in DocumentationPage.query.filter_by(is_published=True).all():
        if page.tags:
            all_tags.extend(page.tags)
    unique_tags = sorted(list(set(all_tags)))
    
    return render_template('documentation/index.html',
                         pages=pages,
                         search_query=search_query,
                         category_filter=category_filter,
                         tag_filter=tag_filter,
                         sort_by=sort_by,
                         categories=categories,
                         tags=unique_tags)


@documentation_bp.route('/view/<slug>')
@login_required
def view(slug):
    """View a single documentation page by slug"""
    page = DocumentationPage.query.filter_by(slug=slug).first_or_404()
    
    # Check visibility
    if not page.is_visible_to_user(current_user):
        flash('You do not have permission to view this documentation page.', 'danger')
        return redirect(url_for('documentation.index'))
    
    # Only increment view count for published pages
    if page.is_published:
        page.increment_view_count()
    
    return render_template('documentation/view.html', page=page)


@documentation_bp.route('/admin')
@login_required
@role_required('product_owner')
def admin_panel():
    """Admin panel for Product Owner to manage all documentation"""
    pages = DocumentationPage.query.order_by(DocumentationPage.created_at.desc()).all()
    
    # Get statistics
    total_pages = len(pages)
    published_pages = len([p for p in pages if p.is_published])
    draft_pages = total_pages - published_pages
    
    # Get categories
    categories = db.session.query(DocumentationPage.category).distinct().all()
    categories = [cat[0] for cat in categories if cat[0]]
    
    delete_form = DeleteForm()
    
    return render_template('documentation/admin.html',
                         pages=pages,
                         total_pages=total_pages,
                         published_pages=published_pages,
                         draft_pages=draft_pages,
                         categories=categories,
                         delete_form=delete_form)


@documentation_bp.route('/admin/create', methods=['GET', 'POST'])
@login_required
@role_required('product_owner')
def create():
    """Create a new documentation page"""
    form = DocumentationPageForm()
    
    if form.validate_on_submit():
        # Handle tags - convert comma-separated string to array
        tags = []
        if form.tags.data:
            tags = [tag.strip() for tag in form.tags.data.split(',') if tag.strip()]
        
        # Determine if published based on which button was clicked
        is_published = form.is_published.data
        if 'save_draft' in request.form:
            is_published = False
        
        # Generate slug from title
        base_slug = DocumentationPage.generate_slug(form.title.data)
        slug = base_slug
        counter = 1
        # Ensure uniqueness
        while DocumentationPage.query.filter_by(slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        page = DocumentationPage(
            title=form.title.data,
            slug=slug,
            content=form.content.data,
            category=form.category.data,
            tags=tags if tags else None,
            visible_roles=form.visible_roles.data if form.visible_roles.data else None,
            is_published=is_published,
            created_by=current_user.id,
            updated_by=current_user.id
        )
        
        db.session.add(page)
        db.session.commit()
        
        flash(f'Documentation page "{page.title}" has been created successfully!', 'success')
        return redirect(url_for('documentation.admin_panel'))
    
    return render_template('documentation/edit.html', form=form, is_create=True)


@documentation_bp.route('/admin/edit/<int:page_id>', methods=['GET', 'POST'])
@login_required
@role_required('product_owner')
def edit(page_id):
    """Edit an existing documentation page"""
    page = DocumentationPage.query.get_or_404(page_id)
    form = DocumentationPageForm(obj=page)
    
    # Convert tags array to comma-separated string for form
    if page.tags:
        form.tags.data = ', '.join(page.tags)
    
    # Set visible_roles
    if page.visible_roles:
        form.visible_roles.data = page.visible_roles
    
    if form.validate_on_submit():
        # Handle tags
        tags = []
        if form.tags.data:
            tags = [tag.strip() for tag in form.tags.data.split(',') if tag.strip()]
        
        # Determine if published
        is_published = form.is_published.data
        if 'save_draft' in request.form:
            is_published = False
        
        # Update slug if title changed
        if page.title != form.title.data:
            base_slug = DocumentationPage.generate_slug(form.title.data)
            slug = base_slug
            counter = 1
            # Ensure uniqueness (excluding current page)
            while DocumentationPage.query.filter_by(slug=slug).filter(DocumentationPage.id != page.id).first():
                slug = f"{base_slug}-{counter}"
                counter += 1
            page.slug = slug
        
        page.title = form.title.data
        page.content = form.content.data
        page.category = form.category.data
        page.tags = tags if tags else None
        page.visible_roles = form.visible_roles.data if form.visible_roles.data else None
        page.is_published = is_published
        page.updated_by = current_user.id
        page.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        flash(f'Documentation page "{page.title}" has been updated successfully!', 'success')
        return redirect(url_for('documentation.admin_panel'))
    
    return render_template('documentation/edit.html', form=form, page=page, is_create=False)


@documentation_bp.route('/admin/delete/<int:page_id>', methods=['POST'])
@login_required
@role_required('product_owner')
def delete(page_id):
    """Delete a documentation page"""
    form = DeleteForm()
    if form.validate_on_submit():
        page = DocumentationPage.query.get_or_404(page_id)
        title = page.title
        db.session.delete(page)
        db.session.commit()
        flash(f'Documentation page "{title}" has been deleted successfully.', 'success')
    else:
        flash('Invalid request or session expired. Please try again.', 'danger')
    return redirect(url_for('documentation.admin_panel'))


@documentation_bp.route('/admin/toggle-publish/<int:page_id>', methods=['POST'])
@login_required
@role_required('product_owner')
def toggle_publish(page_id):
    """Toggle publish status of a documentation page"""
    # Validate CSRF token
    from flask_wtf.csrf import validate_csrf
    from werkzeug.exceptions import BadRequest
    
    try:
        validate_csrf(request.form.get('csrf_token'))
    except BadRequest:
        flash('Invalid request or session expired. Please try again.', 'danger')
        return redirect(url_for('documentation.admin_panel'))
    
    page = DocumentationPage.query.get_or_404(page_id)
    page.is_published = not page.is_published
    page.updated_by = current_user.id
    page.updated_at = datetime.utcnow()
    db.session.commit()
    
    status = 'published' if page.is_published else 'unpublished'
    flash(f'Documentation page "{page.title}" has been {status}.', 'success')
    return redirect(url_for('documentation.admin_panel'))


@documentation_bp.route('/admin/upload-image', methods=['POST'])
@login_required
@role_required('product_owner')
def upload_image():
    """Handle image uploads for documentation content"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Add timestamp to avoid conflicts
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        
        # Create uploads directory if it doesn't exist
        upload_dir = os.path.join('static', 'uploads', 'documentation')
        os.makedirs(upload_dir, exist_ok=True)
        
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)
        
        # Return URL for the image
        image_url = url_for('static', filename=f'uploads/documentation/{filename}')
        return jsonify({'url': image_url}), 200
    
    return jsonify({'error': 'Invalid file type'}), 400


@documentation_bp.route('/api/categories')
@login_required
def api_categories():
    """API endpoint to get all categories"""
    categories = db.session.query(DocumentationPage.category).distinct().all()
    categories = [cat[0] for cat in categories if cat[0]]
    return jsonify(categories)


@documentation_bp.route('/api/tags')
@login_required
def api_tags():
    """API endpoint to get all tags"""
    all_tags = []
    for page in DocumentationPage.query.filter_by(is_published=True).all():
        if page.tags:
            all_tags.extend(page.tags)
    unique_tags = sorted(list(set(all_tags)))
    return jsonify(unique_tags)

