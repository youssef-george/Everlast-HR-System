@final_report_bp.route('/final-report')
@login_required
@role_required(['admin', 'product_owner'])
def final_report():
    """Final Report - Admin only attendance report with auto-fetch and duplicate removal"""
    
    try:
        # Clean up orphaned paid holiday records before processing
        from routes.attendance import cleanup_orphaned_paid_holiday_records
        with current_app.app_context():
            cleanup_orphaned_paid_holiday_records()
    except Exception as e:
        logging.error(f'Error cleaning up paid holiday records: {str(e)}')
    
    # Auto-sync data from devices
    if not is_sync_running():
        try:
            from routes.attendance import sync_attendance_task
            def sync_task():
                try:
                    with current_app.app_context():
                        sync_attendance_task(full_sync=True)
                except Exception as e:
                    logging.error(f'Error auto-syncing data on final report page load: {str(e)}')
            
            sync_thread = threading.Thread(target=sync_task, daemon=True)
            sync_thread.start()
        except Exception as e:
            logging.error(f'Error starting sync thread for final report: {str(e)}')
    else:
        logging.info('Skipping sync on final report page load - another sync is already running')
    
    # Get all active users (admin only) - needed for both empty and populated states
    users = User.query.filter(
        User.status == 'active',
        ~User.first_name.like('User%'),  # Exclude generic test users
        ~User.first_name.like('NN-%'),   # Exclude numbered test users
        User.first_name != '',           # Exclude empty names
        User.last_name != ''             # Exclude users without last names
    ).all()
    
    # Get date range from query parameters (no default - user must choose)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    user_ids = request.args.getlist('user_ids', type=int)
    
    # Only process if dates are provided
    if not start_date_str or not end_date_str:
        # Return empty report if no dates provided
        return render_template('final_report/index.html', 
                             users=users, 
                             start_date=None, 
                             end_date=None, 
                             all_user_reports=[])
    
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    
    # Ensure all attendance logs are processed into DailyAttendance records (optional, for performance)
    process_logs = request.args.get('process_logs', 'true').lower() == 'true'
    if process_logs:
        try:
            ensure_attendance_logs_processed(start_date, end_date)
        except Exception as e:
            logging.error(f"Error processing attendance logs: {str(e)}")
            # Rollback any pending transactions and continue with report generation
            db.session.rollback()
    
    # Filter users if specific users are selected
    if user_ids:
        users = [user for user in users if user.id in user_ids]
    
    # Sorting is not needed for summary view
    
    # Generate report data using unified calculation logic
    all_user_reports = []
    
    for user in users:
        # Use the unified calculation function to ensure exact same logic across all reports
        user_report = calculate_unified_report_data(user, start_date, end_date)
        
        # Use the unified calculation result
        summary_metrics = user_report.summary_metrics
        
        # Create report data with duplicate removal (using unified function results)
        report_data = []
        
        # Add attendance records
        for record in user_report.attendance_records:
            report_data.append({
                'date': record.date,
                'status': record.status,
                'check_in': record.first_check_in,
                'check_out': record.last_check_out,
                'hours_worked': (record.last_check_out - record.first_check_in).total_seconds() / 3600 if record.first_check_in and record.last_check_out else 0,
                'extra_time': (record.last_check_out - record.first_check_in).total_seconds() / 3600 - 9 if record.first_check_in and record.last_check_out else 0
            })
        
        # Add leave requests
        for leave_request in user_report.leave_requests:
            # Calculate days within the date range
            leave_start = max(leave_request.start_date, start_date)
            leave_end = min(leave_request.end_date, end_date)
            if leave_start <= leave_end:
                # Add each day of the leave
                current_leave_date = leave_start
                while current_leave_date <= leave_end:
                    report_data.append({
                        'date': current_leave_date,
                        'status': 'Leave',
                        'check_in': None,
                        'check_out': None,
                        'hours_worked': 0,
                        'extra_time': 0,
                        'leave_type': leave_request.leave_type.name if leave_request.leave_type else 'Unknown',
                        'leave_reason': leave_request.reason
                    })
                    current_leave_date += timedelta(days=1)
        
        # Add permission requests
        for permission_request in user_report.permission_requests:
            # Calculate days within the date range
            perm_start = max(permission_request.start_time, datetime.combine(start_date, datetime.min.time()))
            perm_end = min(permission_request.end_time, datetime.combine(end_date, datetime.max.time()))
            if perm_start <= perm_end:
                # Add each day of the permission
                current_perm_date = perm_start.date()
                while current_perm_date <= perm_end.date():
                    if current_perm_date >= start_date and current_perm_date <= end_date:
                        report_data.append({
                            'date': current_perm_date,
                            'status': 'Permission',
                            'check_in': None,
                            'check_out': None,
                            'hours_worked': 0,
                            'extra_time': 0,
                            'permission_reason': permission_request.reason,
                            'permission_start': permission_request.start_time,
                            'permission_end': permission_request.end_time
                        })
                    current_perm_date += timedelta(days=1)
        
        # No sorting needed for summary view
        
        all_user_reports.append({
            'user': user,
            'summary_metrics': summary_metrics,
            'report_data': report_data
        })
    
    try:
        return render_template('final_report/index.html', 
                             users=users, 
                             start_date=start_date, 
                             end_date=end_date, 
                             all_user_reports=all_user_reports)
    except Exception as e:
        logging.error(f'Error rendering final report template: {str(e)}')
        return render_template('final_report/index.html', 
                             users=[], 
                             start_date=start_date, 
                             end_date=end_date, 
                             all_user_reports=[],
                             error_message=f"Error loading report: {str(e)}")
