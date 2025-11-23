# Everlast ERP System Project – HR Platform

**Last Update:** December 2024

**Latest Features Added:** Ticketing System Module

---

## Project Definition

The Everlast ERP System is an internal HR platform designed to centrally manage employee attendance, leave requests, and permissions across all departments.

It integrates seamlessly with biometric devices and enforces structured, multi-level approval workflows to ensure transparency and compliance.

The system replaces manual or paper-based tracking with automated digital processes, improving efficiency, accuracy, and HR governance.

## Project Components

The system includes the following key modules:

### • User & Role Management

- Role-based system with access control
- User roles include:
  - Employee, Direct Manager, HR, General Manager, and Admin
- Permissions and data visibility are strictly based on roles

In addition to roles and permissions, the system includes a **Company Members Directory**:

- Lists all employees with details: fingerprint ID, Avaya number, email, employee code.
- Searchable and sortable for quick access and HR coordination.
- Helps facilitate communication and attendance tracking across departments.

### • Attendance Module

- Automated real-time sync with fingerprint devices
- Tracks:
  - Check-in / Check-out
  - Working hours
  - Late arrivals / Early departures
  - Absence and incomplete logs

### • Leave & Permission Requests

- Leave and short permission workflows
- Multi-step approval:
  - Direct Manager → HR → General Manager → Admin
- Leave types include:
  - Annual, Sick, Paid, Emergency, etc.
- Tracks approval status and request history

### • Device Integration

- Configurable biometric device sync via IP and Port
- Auto-sync every 300 seconds
- Admin can test connection and fetch data manually if needed

### • Calendar & Reporting

Each employee has a personal calendar showing:

- Attendance records
- Leave & permission status
- Color-coded: Green = Approved, Red = Rejected, Yellow = Pending
- Dynamic departmental analytics and request statistics

### • Admin Dashboard

Displays live system metrics:

- Pending leave/permission requests
- Attendance anomalies
- Device status
- Department-wise statistics

### • Ticketing System (NEW)

A comprehensive internal support ticket management system for handling IT requests, technical issues, and department-specific inquiries:

**Core Features:**

- **Ticket Submission:**
  - Employees can submit tickets with title, description, and priority levels (Low, Medium, High, Critical)
  - Support for file attachments (images, documents, archives - up to 10MB)
  - Automatic routing to appropriate departments based on ticket category

- **Ticket Categories & Routing:**
  - Product Owner manages ticket categories
  - Each category can be assigned to specific departments (IT/Web)
  - Automatic ticket routing to assigned departments upon submission

- **Role-Based Access:**
  - **Employees:** Can view and submit their own tickets
  - **IT/Web Department:** Access to department inbox with all tickets assigned to their department
  - **Product Owner/Admin:** Full access to all tickets via manager dashboard

- **Ticket Management:**
  - Status tracking: Open → In Progress → Resolved → Closed
  - Priority-based filtering and sorting
  - Status history with change tracking
  - Ticket deletion (Product Owner only)

- **Comments & Communication:**
  - Public comments visible to ticket requester
  - Internal comments (visible only to IT/Web departments and admins)
  - File attachments on comments
  - Real-time email notifications for all ticket activities

- **Email Notifications:**
  - Automated emails for ticket creation, replies, status updates, and resolution
  - Customizable email templates (Product Owner managed)
  - Notifications sent to requesters and assigned departments

- **Department Inbox:**
  - IT/Web departments have dedicated inbox view
  - Filter by status, priority, and category
  - Quick access to all tickets requiring attention

- **Manager Dashboard:**
  - Product Owner and Admin overview of all tickets
  - Statistics: Total, Open, In Progress, Resolved, Closed tickets
  - Critical and high-priority ticket tracking
  - Advanced filtering capabilities

- **File Attachments:**
  - Support for multiple file types (images, PDFs, documents, archives)
  - Secure file storage and download
  - Attachment size limit: 10MB per file

## Project Objective

- Digitize and streamline internal HR and attendance operations
- Replace manual/paper forms with real-time digital workflows
- Improve visibility over staff presence, scheduling, and compliance
- Enable faster approvals and centralized reporting
- Enhance HR transparency and accountability

## Project Scope

- Covers all departments: HR, Web Development, IT, Finance, Admin, Marketing, etc.
- Supports all employment types: Full-time, part-time, temp staff
- Includes:
  - Daily biometric attendance
  - Leave & absence tracking
  - Permission workflows
  - Departmental-level insights
  - Internal ticketing system for IT support and technical requests

## Required Resources

- Biometric fingerprint device(s) with SDK or IP access
- Local server or machine hosting the system
- Technologies used:
  - Python, Flask Backend
  - SQLite3 for Database
  - Bootstrap or Metronic Frontend
- Internal network connectivity to device(s)
- AI Agent support (Trae) for agile development, automation, and enhancement

---

## Recent Updates (December 2024)

### Ticketing System Module

Added a complete internal support ticket management system to streamline IT support and technical request handling:

- **Employee Ticket Submission:** Easy-to-use form for submitting support requests with priority levels and file attachments
- **Smart Routing:** Automatic ticket routing to appropriate departments based on category
- **Department Inbox:** Dedicated inbox for IT/Web departments to manage assigned tickets
- **Manager Dashboard:** Comprehensive overview for Product Owners and Admins with statistics and filtering
- **Email Integration:** Automated email notifications for all ticket activities with customizable templates
- **Internal Notes:** Support for internal comments visible only to support staff
- **File Attachments:** Secure file upload and download system for tickets and comments
- **Status Tracking:** Complete lifecycle management from creation to resolution

This module enhances internal communication, improves response times, and provides better tracking of technical requests and IT support activities.

---

**Document Version:** 2.0  
**Last Updated:** December 2024

