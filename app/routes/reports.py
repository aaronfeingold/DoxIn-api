"""
Reports routes for admin analytics and custom reports
"""
from flask import Blueprint, jsonify, request, send_file, current_app
from app import db
from app.models.report import Report, SavedReportTemplate
from app.models.user import User
from app.utils.auth import require_auth, admin_required, get_current_user, is_admin
from app.services.report_service import ReportService
from sqlalchemy import func
from datetime import datetime, timedelta
from pathlib import Path
import os

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/', methods=['GET'])
@require_auth
@admin_required
def list_reports():
    """List all reports with pagination and filtering"""
    try:
        current_user = get_current_user()

        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        report_type = request.args.get('type')
        status = request.args.get('status')
        user_id = request.args.get('user_id')

        # Build query
        query = Report.query

        # Apply filters
        if report_type:
            query = query.filter(Report.report_type == report_type)
        if status:
            query = query.filter(Report.status == status)
        if user_id:
            query = query.filter(Report.user_id == user_id)

        # Get paginated results
        reports = query.order_by(Report.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        # Get statistics
        stats = db.session.query(
            Report.status,
            func.count(Report.id).label('count')
        ).group_by(Report.status).all()

        return jsonify({
            'reports': [{
                'id': r.id,
                'report_type': r.report_type,
                'status': r.status,
                'parameters': r.parameters,
                'file_path': r.file_path,
                'created_at': r.created_at.isoformat() if r.created_at else None,
                'completed_at': r.completed_at.isoformat() if r.completed_at else None,
                'user_id': r.user_id,
                'error_message': r.error_message
            } for r in reports.items],
            'pagination': {
                'page': reports.page,
                'per_page': reports.per_page,
                'total': reports.total,
                'pages': reports.pages
            },
            'statistics': {status: count for status, count in stats}
        })

    except Exception as e:
        current_app.logger.error(f"Error listing reports: {str(e)}")
        return jsonify({'error': 'Failed to list reports'}), 500


@reports_bp.route('/generate', methods=['POST'])
@require_auth
@admin_required
def generate_report():
    """Generate a new report"""
    try:
        data = request.get_json()
        current_user = get_current_user()

        report_type = data.get('report_type')
        parameters = data.get('parameters', {})

        if not report_type:
            return jsonify({'error': 'report_type is required'}), 400

        # Create report record
        report = Report(
            report_type=report_type,
            status='pending',
            parameters=parameters,
            user_id=current_user.id
        )
        db.session.add(report)
        db.session.commit()

        # Generate report based on type
        service = ReportService(db.session)

        try:
            if report_type == 'financial':
                result = service.generate_financial_report(parameters)
            elif report_type == 'sales':
                result = service.generate_sales_report(parameters)
            elif report_type == 'business_intelligence':
                result = service.generate_business_intelligence_report(parameters)
            elif report_type == 'profit_margin':
                result = service.generate_profit_margin_analysis(parameters)
            else:
                return jsonify({'error': f'Unknown report type: {report_type}'}), 400

            # Update report with results
            report.status = 'completed'
            report.file_path = result.get('file_path')
            report.result_data = result.get('metrics')
            report.completed_at = datetime.utcnow()
            db.session.commit()

            return jsonify({
                'id': report.id,
                'status': report.status,
                'file_path': report.file_path,
                'metrics': result.get('metrics'),
                'message': 'Report generated successfully'
            })

        except Exception as e:
            report.status = 'failed'
            report.error_message = str(e)
            db.session.commit()
            raise

    except Exception as e:
        current_app.logger.error(f"Error generating report: {str(e)}")
        return jsonify({'error': 'Failed to generate report'}), 500


@reports_bp.route('/<report_id>', methods=['GET'])
@require_auth
@admin_required
def get_report(report_id):
    """Get report details"""
    try:
        report = Report.query.get(report_id)

        if not report:
            return jsonify({'error': 'Report not found'}), 404

        return jsonify({
            'id': report.id,
            'report_type': report.report_type,
            'status': report.status,
            'parameters': report.parameters,
            'result_data': report.result_data,
            'file_path': report.file_path,
            'created_at': report.created_at.isoformat() if report.created_at else None,
            'completed_at': report.completed_at.isoformat() if report.completed_at else None,
            'error_message': report.error_message
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching report: {str(e)}")
        return jsonify({'error': 'Failed to fetch report'}), 500


@reports_bp.route('/<report_id>/download', methods=['GET'])
@require_auth
@admin_required
def download_report(report_id):
    """Download report file"""
    try:
        report = Report.query.get(report_id)

        if not report:
            return jsonify({'error': 'Report not found'}), 404

        if not report.file_path or not os.path.exists(report.file_path):
            return jsonify({'error': 'Report file not found'}), 404

        return send_file(
            report.file_path,
            as_attachment=True,
            download_name=f"{report.report_type}_report_{report.id}.png"
        )

    except Exception as e:
        current_app.logger.error(f"Error downloading report: {str(e)}")
        return jsonify({'error': 'Failed to download report'}), 500


@reports_bp.route('/<report_id>', methods=['DELETE'])
@require_auth
@admin_required
def delete_report(report_id):
    """Delete a report"""
    try:
        report = Report.query.get(report_id)

        if not report:
            return jsonify({'error': 'Report not found'}), 404

        # Delete file if exists
        if report.file_path and os.path.exists(report.file_path):
            os.remove(report.file_path)

        db.session.delete(report)
        db.session.commit()

        return jsonify({'message': 'Report deleted successfully'})

    except Exception as e:
        current_app.logger.error(f"Error deleting report: {str(e)}")
        return jsonify({'error': 'Failed to delete report'}), 500


# ========================================
# REPORT TEMPLATES
# ========================================

@reports_bp.route('/templates', methods=['GET'])
@require_auth
@admin_required
def list_templates():
    """List all saved report templates"""
    try:
        templates = SavedReportTemplate.query.order_by(SavedReportTemplate.created_at.desc()).all()

        return jsonify({
            'templates': [{
                'id': t.id,
                'name': t.name,
                'description': t.description,
                'report_type': t.report_type,
                'parameters': t.parameters,
                'created_at': t.created_at.isoformat() if t.created_at else None
            } for t in templates]
        })

    except Exception as e:
        current_app.logger.error(f"Error listing templates: {str(e)}")
        return jsonify({'error': 'Failed to list templates'}), 500


@reports_bp.route('/templates', methods=['POST'])
@require_auth
@admin_required
def create_template():
    """Create a new report template"""
    try:
        data = request.get_json()
        current_user = get_current_user()

        template = SavedReportTemplate(
            name=data.get('name'),
            description=data.get('description'),
            report_type=data.get('report_type'),
            parameters=data.get('parameters', {}),
            created_by_user_id=current_user.id
        )

        db.session.add(template)
        db.session.commit()

        return jsonify({
            'id': template.id,
            'name': template.name,
            'message': 'Template created successfully'
        })

    except Exception as e:
        current_app.logger.error(f"Error creating template: {str(e)}")
        return jsonify({'error': 'Failed to create template'}), 500


@reports_bp.route('/templates/<template_id>', methods=['DELETE'])
@require_auth
@admin_required
def delete_template(template_id):
    """Delete a report template"""
    try:
        template = SavedReportTemplate.query.get(template_id)

        if not template:
            return jsonify({'error': 'Template not found'}), 404

        db.session.delete(template)
        db.session.commit()

        return jsonify({'message': 'Template deleted successfully'})

    except Exception as e:
        current_app.logger.error(f"Error deleting template: {str(e)}")
        return jsonify({'error': 'Failed to delete template'}), 500


# ========================================
# USER-LEVEL ANALYTICS ENDPOINTS
# ========================================

@reports_bp.route('/analytics/summary', methods=['GET'])
@require_auth
def get_analytics_summary():
    """Get comprehensive analytics summary for the current user"""
    try:
        current_user = get_current_user()
        service = ReportService(db.session)

        # Get analytics data (filtered by user if not admin)
        analytics_data = service.get_analytics_summary(
            user_id=current_user.id,
            is_admin=is_admin()
        )

        return jsonify(analytics_data)

    except Exception as e:
        current_app.logger.error(f"Error fetching analytics summary: {str(e)}")
        return jsonify({'error': 'Failed to fetch analytics summary'}), 500


@reports_bp.route('/analytics/invoice-stats', methods=['GET'])
@require_auth
def get_invoice_stats():
    """Get invoice payment statistics (paid vs unpaid)"""
    try:
        current_user = get_current_user()
        service = ReportService(db.session)

        stats = service.get_invoice_statistics(
            user_id=current_user.id,
            is_admin=is_admin()
        )

        return jsonify(stats)

    except Exception as e:
        current_app.logger.error(f"Error fetching invoice stats: {str(e)}")
        return jsonify({'error': 'Failed to fetch invoice statistics'}), 500


@reports_bp.route('/analytics/top-companies', methods=['GET'])
@require_auth
def get_top_companies_analytics():
    """Get top companies by invoice count and revenue"""
    try:
        current_user = get_current_user()
        service = ReportService(db.session)

        # Get limit from query params
        limit = min(request.args.get('limit', 10, type=int), 50)

        companies = service.get_top_companies(
            user_id=current_user.id,
            is_admin=is_admin(),
            limit=limit
        )

        return jsonify(companies)

    except Exception as e:
        current_app.logger.error(f"Error fetching top companies: {str(e)}")
        return jsonify({'error': 'Failed to fetch top companies'}), 500


@reports_bp.route('/analytics/trends', methods=['GET'])
@require_auth
def get_monthly_trends():
    """Get monthly invoice and revenue trends"""
    try:
        current_user = get_current_user()
        service = ReportService(db.session)

        # Get months from query params (default 12)
        months = min(request.args.get('months', 12, type=int), 36)

        trends = service.get_monthly_trends(
            user_id=current_user.id,
            is_admin=is_admin(),
            months=months
        )

        return jsonify(trends)

    except Exception as e:
        current_app.logger.error(f"Error fetching trends: {str(e)}")
        return jsonify({'error': 'Failed to fetch monthly trends'}), 500


# ========================================
# ADMIN-LEVEL ADVANCED ANALYTICS
# ========================================

@reports_bp.route('/analytics/executive-dashboard', methods=['GET'])
@require_auth
@admin_required
def get_executive_dashboard():
    """Get executive dashboard with comprehensive KPIs (admin only)"""
    try:
        service = ReportService(db.session)
        dashboard_data = service.get_executive_dashboard()

        return jsonify(dashboard_data)

    except Exception as e:
        current_app.logger.error(f"Error fetching executive dashboard: {str(e)}")
        return jsonify({'error': 'Failed to fetch executive dashboard'}), 500


@reports_bp.route('/analytics/customer-analytics', methods=['GET'])
@require_auth
@admin_required
def get_customer_analytics():
    """Get customer value analysis (admin only)"""
    try:
        service = ReportService(db.session)

        # Get limit from query params
        limit = min(request.args.get('limit', 20, type=int), 100)

        customer_data = service.get_customer_analytics(limit=limit)

        return jsonify(customer_data)

    except Exception as e:
        current_app.logger.error(f"Error fetching customer analytics: {str(e)}")
        return jsonify({'error': 'Failed to fetch customer analytics'}), 500


@reports_bp.route('/analytics/product-performance', methods=['GET'])
@require_auth
@admin_required
def get_product_performance():
    """Get product performance analysis (admin only)"""
    try:
        service = ReportService(db.session)

        # Get limit from query params
        limit = min(request.args.get('limit', 20, type=int), 100)

        product_data = service.get_product_performance(limit=limit)

        return jsonify(product_data)

    except Exception as e:
        current_app.logger.error(f"Error fetching product performance: {str(e)}")
        return jsonify({'error': 'Failed to fetch product performance'}), 500


# ========================================
# ADVANCED ANALYSIS REPORT ENDPOINTS
# ========================================

@reports_bp.route('/generate/business-intelligence', methods=['POST'])
@require_auth
@admin_required
def generate_business_intelligence_report():
    """
    Generate comprehensive business intelligence report with visualizations

    Request body:
    {
        "start_date": "2023-01-01",  // optional
        "end_date": "2023-12-31"      // optional
    }

    Returns report ID, metrics, and file paths for download
    """
    try:
        data = request.get_json() or {}
        current_user = get_current_user()

        # Create report record
        report = Report(
            report_type='business_intelligence',
            status='pending',
            parameters=data,
            user_id=current_user.id
        )
        db.session.add(report)
        db.session.commit()

        # Generate report
        service = ReportService(db.session)

        try:
            result = service.generate_business_intelligence_report(data)

            # Update report with results
            report.status = 'completed'
            report.file_path = result.get('file_path')
            report.result_data = result.get('metrics')
            report.completed_at = datetime.utcnow()
            db.session.commit()

            return jsonify({
                'id': report.id,
                'status': report.status,
                'file_path': report.file_path,
                'additional_files': result.get('additional_files', []),
                'metrics': result.get('metrics'),
                'message': 'Business intelligence report generated successfully'
            })

        except Exception as e:
            report.status = 'failed'
            report.error_message = str(e)
            db.session.commit()
            raise

    except Exception as e:
        current_app.logger.error(f"Error generating business intelligence report: {str(e)}")
        return jsonify({'error': 'Failed to generate business intelligence report', 'details': str(e)}), 500


@reports_bp.route('/generate/profit-margin', methods=['POST'])
@require_auth
@admin_required
def generate_profit_margin_report():
    """
    Generate profit margin and break-even analysis report

    Request body:
    {
        "start_date": "2023-01-01",  // optional
        "end_date": "2023-12-31"      // optional
    }

    Returns detailed cost vs price analysis with break-even calculations
    """
    try:
        data = request.get_json() or {}
        current_user = get_current_user()

        # Create report record
        report = Report(
            report_type='profit_margin',
            status='pending',
            parameters=data,
            user_id=current_user.id
        )
        db.session.add(report)
        db.session.commit()

        # Generate report
        service = ReportService(db.session)

        try:
            result = service.generate_profit_margin_analysis(data)

            # Update report with results
            report.status = 'completed'
            report.file_path = result.get('file_path')
            report.result_data = result.get('metrics')
            report.completed_at = datetime.utcnow()
            db.session.commit()

            return jsonify({
                'id': report.id,
                'status': report.status,
                'file_path': report.file_path,
                'metrics': result.get('metrics'),
                'message': 'Profit margin analysis report generated successfully'
            })

        except Exception as e:
            report.status = 'failed'
            report.error_message = str(e)
            db.session.commit()
            raise

    except Exception as e:
        current_app.logger.error(f"Error generating profit margin report: {str(e)}")
        return jsonify({'error': 'Failed to generate profit margin report', 'details': str(e)}), 500


@reports_bp.route('/<report_id>/files', methods=['GET'])
@require_auth
@admin_required
def get_report_files(report_id):
    """
    Get all files associated with a report (for multi-file reports like business intelligence)

    Returns a list of available files and their paths
    """
    try:
        report = Report.query.get(report_id)

        if not report:
            return jsonify({'error': 'Report not found'}), 404

        if report.status != 'completed':
            return jsonify({'error': 'Report is not completed yet'}), 400

        # Get the directory of the main report file
        if not report.file_path or not os.path.exists(report.file_path):
            return jsonify({'error': 'Report file not found'}), 404

        file_dir = os.path.dirname(report.file_path)
        base_filename = os.path.basename(report.file_path)

        # Extract timestamp from filename to find related files
        # Format: business_sales_analysis_YYYYMMDD_HHMMSS.png
        parts = base_filename.split('_')

        # Look for all files with similar timestamp
        available_files = []

        # Add main file
        available_files.append({
            'name': base_filename,
            'path': report.file_path,
            'type': 'main',
            'download_url': f'/api/reports/{report_id}/download'
        })

        # Look for related files (operational insights, etc.)
        if os.path.isdir(file_dir):
            for filename in os.listdir(file_dir):
                filepath = os.path.join(file_dir, filename)
                # Check if file is related (contains similar timestamp or report type)
                if filepath != report.file_path and os.path.isfile(filepath):
                    # Check if file was created around the same time (within 1 minute)
                    main_time = os.path.getmtime(report.file_path)
                    file_time = os.path.getmtime(filepath)

                    if abs(main_time - file_time) < 60:  # Within 60 seconds
                        available_files.append({
                            'name': filename,
                            'path': filepath,
                            'type': 'additional',
                            'download_url': f'/api/reports/{report_id}/download/{filename}'
                        })

        return jsonify({
            'report_id': report_id,
            'report_type': report.report_type,
            'files': available_files,
            'total_files': len(available_files)
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching report files: {str(e)}")
        return jsonify({'error': 'Failed to fetch report files'}), 500


@reports_bp.route('/<report_id>/download/<filename>', methods=['GET'])
@require_auth
@admin_required
def download_specific_file(report_id, filename):
    """Download a specific file from a multi-file report"""
    try:
        report = Report.query.get(report_id)

        if not report:
            return jsonify({'error': 'Report not found'}), 404

        if not report.file_path:
            return jsonify({'error': 'Report has no files'}), 404

        # Get directory and construct file path
        file_dir = os.path.dirname(report.file_path)
        file_path = os.path.join(file_dir, filename)

        # Security check: ensure file is in the same directory as report
        if not os.path.exists(file_path) or not file_path.startswith(file_dir):
            return jsonify({'error': 'File not found'}), 404

        # Verify file was created around the same time as the report
        main_time = os.path.getmtime(report.file_path)
        file_time = os.path.getmtime(file_path)

        if abs(main_time - file_time) > 60:  # More than 60 seconds apart
            return jsonify({'error': 'File not associated with this report'}), 403

        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        current_app.logger.error(f"Error downloading file: {str(e)}")
        return jsonify({'error': 'Failed to download file'}), 500
