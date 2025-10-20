"""
Report generation service - ports logic from discovery scripts to work with SQL database
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from sqlalchemy import func, extract
from decimal import Decimal
import warnings
warnings.filterwarnings('ignore')


class ReportService:
    """Service for generating various admin reports"""

    def __init__(self, db_session, output_dir='/tmp/reports'):
        self.db = db_session
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)

    def generate_financial_report(self, params):
        """
        Generate financial analysis report (profit margins, cost vs price, break-even)

        Args:
            params: dict with date_range, category_filter, etc.

        Returns:
            dict with file_path, metrics, etc.
        """
        # Import matplotlib only when generating chart reports
        import matplotlib.pyplot as plt
        import seaborn as sns
        from matplotlib.ticker import FuncFormatter

        def currency_formatter(x, p):
            """Format numbers as currency"""
            if abs(x) >= 1e6:
                return f'${x/1e6:.1f}M'
            elif abs(x) >= 1e3:
                return f'${x/1e3:.0f}K'
            else:
                return f'${x:.0f}'

        from app.models import Invoice, InvoiceLineItem, Product, ProductCategory, ProductSubCategory

        # Build query with filters
        query = self.db.query(
            InvoiceLineItem.quantity,
            InvoiceLineItem.unit_price,
            InvoiceLineItem.line_total,
            Product.name.label('product_name'),
            Product.standard_cost,
            Product.list_price,
            ProductCategory.name.label('category_name'),
            Invoice.invoice_date
        ).join(
            Invoice, InvoiceLineItem.invoice_id == Invoice.id
        ).join(
            Product, InvoiceLineItem.product_id == Product.id
        ).join(
            ProductSubCategory, Product.subcategory_id == ProductSubCategory.subcategory_id
        ).join(
            ProductCategory, ProductSubCategory.category_id == ProductCategory.category_id
        )

        # Apply date filter
        if params.get('start_date'):
            query = query.filter(Invoice.invoice_date >= params['start_date'])
        if params.get('end_date'):
            query = query.filter(Invoice.invoice_date <= params['end_date'])

        # Apply category filter
        if params.get('category_ids'):
            query = query.filter(ProductCategory.category_id.in_(params['category_ids']))

        # Execute query and convert to DataFrame
        df = pd.read_sql(query.statement, self.db.bind)

        if df.empty:
            return {'error': 'No data found for the specified filters'}

        # Calculate profit metrics
        df['revenue'] = df['line_total']
        df['cost'] = df['quantity'] * df['standard_cost']
        df['profit'] = df['revenue'] - df['cost']
        df['profit_margin_pct'] = (df['profit'] / df['revenue']) * 100

        # Create visualizations
        fig, axes = plt.subplots(2, 2, figsize=(20, 16))
        fig.suptitle('Financial Performance Analysis', fontsize=20, fontweight='bold')

        # 1. Profit margin by category
        category_margins = df.groupby('category_name').agg({
            'profit_margin_pct': 'mean',
            'revenue': 'sum',
            'profit': 'sum'
        }).sort_values('profit_margin_pct', ascending=True)

        ax1 = axes[0, 0]
        colors = ['#E74C3C' if x < 30 else '#F39C12' if x < 50 else '#27AE60'
                  for x in category_margins['profit_margin_pct']]
        bars = ax1.barh(category_margins.index, category_margins['profit_margin_pct'], color=colors)
        ax1.set_title('Profit Margin by Category', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Profit Margin (%)', fontsize=12)

        # 2. Revenue vs Cost by Category
        ax2 = axes[0, 1]
        category_totals = df.groupby('category_name').agg({
            'revenue': 'sum',
            'cost': 'sum'
        }).sort_values('revenue', ascending=False)

        x = np.arange(len(category_totals))
        width = 0.35
        ax2.bar(x - width/2, category_totals['revenue'], width, label='Revenue', color='#3498DB')
        ax2.bar(x + width/2, category_totals['cost'], width, label='Cost', color='#E74C3C')
        ax2.set_title('Revenue vs Cost by Category', fontsize=14, fontweight='bold')
        ax2.set_ylabel('Amount ($)', fontsize=12)
        ax2.set_xticks(x)
        ax2.set_xticklabels(category_totals.index, rotation=45, ha='right')
        ax2.yaxis.set_major_formatter(FuncFormatter(currency_formatter))
        ax2.legend()

        # 3. Monthly profit trend
        df['invoice_date'] = pd.to_datetime(df['invoice_date'])
        monthly_profit = df.groupby(df['invoice_date'].dt.to_period('M')).agg({
            'revenue': 'sum',
            'profit': 'sum'
        })
        monthly_profit.index = monthly_profit.index.to_timestamp()

        ax3 = axes[1, 0]
        ax3.plot(monthly_profit.index, monthly_profit['revenue'],
                 marker='o', linewidth=2, label='Revenue', color='#3498DB')
        ax3.plot(monthly_profit.index, monthly_profit['profit'],
                 marker='s', linewidth=2, label='Profit', color='#27AE60')
        ax3.set_title('Monthly Revenue & Profit Trend', fontsize=14, fontweight='bold')
        ax3.set_xlabel('Month', fontsize=12)
        ax3.set_ylabel('Amount ($)', fontsize=12)
        ax3.yaxis.set_major_formatter(FuncFormatter(currency_formatter))
        ax3.legend()
        ax3.grid(True, alpha=0.3)

        # 4. Top products by profit
        top_products = df.groupby('product_name').agg({
            'profit': 'sum'
        }).nlargest(10, 'profit')

        ax4 = axes[1, 1]
        ax4.barh(top_products.index, top_products['profit'], color='#9B59B6')
        ax4.set_title('Top 10 Products by Profit', fontsize=14, fontweight='bold')
        ax4.set_xlabel('Total Profit ($)', fontsize=12)
        ax4.xaxis.set_major_formatter(FuncFormatter(currency_formatter))

        plt.tight_layout()

        # Save report
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'financial_report_{timestamp}.png'
        file_path = self.output_dir / filename
        plt.savefig(file_path, dpi=300, bbox_inches='tight')
        plt.close()

        # Calculate summary metrics
        total_revenue = df['revenue'].sum()
        total_cost = df['cost'].sum()
        total_profit = df['profit'].sum()
        overall_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0

        return {
            'file_path': str(file_path),
            'filename': filename,
            'metrics': {
                'total_revenue': float(total_revenue),
                'total_cost': float(total_cost),
                'total_profit': float(total_profit),
                'profit_margin_pct': float(overall_margin),
                'categories_analyzed': len(category_margins),
                'date_range': {
                    'start': params.get('start_date'),
                    'end': params.get('end_date')
                }
            }
        }

    def generate_sales_report(self, params):
        """
        Generate sales performance report (by territory, salesperson, trends)

        Args:
            params: dict with date_range, territory_filter, etc.

        Returns:
            dict with file_path, metrics, etc.
        """
        # Import matplotlib only when generating chart reports
        import matplotlib.pyplot as plt
        import seaborn as sns
        from matplotlib.ticker import FuncFormatter

        def currency_formatter(x, p):
            """Format numbers as currency"""
            if abs(x) >= 1e6:
                return f'${x/1e6:.1f}M'
            elif abs(x) >= 1e3:
                return f'${x/1e3:.0f}K'
            else:
                return f'${x:.0f}'

        from app.models import Invoice, User

        # Build query with filters
        query = self.db.query(
            Invoice.id,
            Invoice.invoice_number,
            Invoice.invoice_date,
            Invoice.total_amount,
            Invoice.uploaded_by_user_id,
            User.email.label('salesperson_email')
        ).join(
            User, Invoice.uploaded_by_user_id == User.id, isouter=True
        )

        # Apply date filter
        if params.get('start_date'):
            query = query.filter(Invoice.invoice_date >= params['start_date'])
        if params.get('end_date'):
            query = query.filter(Invoice.invoice_date <= params['end_date'])

        # Execute query and convert to DataFrame
        df = pd.read_sql(query.statement, self.db.bind)

        if df.empty:
            return {'error': 'No data found for the specified filters'}

        # Create visualizations
        fig, axes = plt.subplots(2, 2, figsize=(20, 16))
        fig.suptitle('Sales Performance Analysis', fontsize=20, fontweight='bold')

        # 1. Sales by territory (using user as proxy)
        territory_sales = df.groupby('salesperson_email').agg({
            'total_amount': 'sum'
        }).nlargest(10, 'total_amount')

        ax1 = axes[0, 0]
        ax1.bar(range(len(territory_sales)), territory_sales['total_amount'], color='#3498DB')
        ax1.set_title('Sales by Territory', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Total Sales ($)', fontsize=12)
        ax1.yaxis.set_major_formatter(FuncFormatter(currency_formatter))

        # 2. Top salespeople
        top_sales = df.groupby('salesperson_email').agg({
            'total_amount': 'sum',
            'id': 'count'
        }).nlargest(10, 'total_amount')

        ax2 = axes[0, 1]
        ax2.barh(range(len(top_sales)), top_sales['total_amount'], color='#27AE60')
        ax2.set_title('Top 10 Salespeople', fontsize=14, fontweight='bold')
        ax2.set_xlabel('Total Sales ($)', fontsize=12)
        ax2.xaxis.set_major_formatter(FuncFormatter(currency_formatter))

        # 3. Sales trend over time
        df['invoice_date'] = pd.to_datetime(df['invoice_date'])
        monthly_sales = df.groupby(df['invoice_date'].dt.to_period('M')).agg({
            'total_amount': 'sum'
        })
        monthly_sales.index = monthly_sales.index.to_timestamp()

        ax3 = axes[1, 0]
        ax3.plot(monthly_sales.index, monthly_sales['total_amount'],
                 marker='o', linewidth=3, color='#E74C3C')
        ax3.set_title('Monthly Sales Trend', fontsize=14, fontweight='bold')
        ax3.set_xlabel('Month', fontsize=12)
        ax3.set_ylabel('Total Sales ($)', fontsize=12)
        ax3.yaxis.set_major_formatter(FuncFormatter(currency_formatter))
        ax3.grid(True, alpha=0.3)

        # 4. Invoice amount distribution
        ax4 = axes[1, 1]
        ax4.hist(df['total_amount'], bins=30, color='#9B59B6', alpha=0.7, edgecolor='black')
        ax4.set_title('Invoice Amount Distribution', fontsize=14, fontweight='bold')
        ax4.set_xlabel('Invoice Amount ($)', fontsize=12)
        ax4.set_ylabel('Frequency', fontsize=12)
        ax4.xaxis.set_major_formatter(FuncFormatter(currency_formatter))

        plt.tight_layout()

        # Save report
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'sales_report_{timestamp}.png'
        file_path = self.output_dir / filename
        plt.savefig(file_path, dpi=300, bbox_inches='tight')
        plt.close()

        # Calculate summary metrics
        total_sales = df['total_amount'].sum()
        num_invoices = len(df)
        avg_invoice = df['total_amount'].mean()
        num_salespeople = df['salesperson_email'].nunique()

        return {
            'file_path': str(file_path),
            'filename': filename,
            'metrics': {
                'total_sales': float(total_sales),
                'num_invoices': num_invoices,
                'avg_invoice_value': float(avg_invoice),
                'num_salespeople': num_salespeople,
                'date_range': {
                    'start': params.get('start_date'),
                    'end': params.get('end_date')
                }
            }
        }

    # ========================================
    # USER-LEVEL ANALYTICS (JSON responses)
    # ========================================

    def get_invoice_statistics(self, user_id=None, is_admin=False):
        """
        Get invoice payment statistics (paid vs unpaid)

        Args:
            user_id: User ID (if not admin, filters to user's invoices)
            is_admin: Whether the user is an admin

        Returns:
            dict with payment status breakdown and metrics
        """
        from app.models import Invoice

        # Build query
        query = self.db.query(
            Invoice.payment_status,
            func.count(Invoice.id).label('count'),
            func.sum(Invoice.total_amount).label('total_amount')
        )

        # Filter by user if not admin
        if not is_admin and user_id:
            query = query.filter(Invoice.uploaded_by_user_id == user_id)

        query = query.group_by(Invoice.payment_status)
        results = query.all()

        # Get totals
        total_query = self.db.query(
            func.count(Invoice.id).label('total_count'),
            func.sum(Invoice.total_amount).label('total_amount'),
            func.avg(Invoice.total_amount).label('avg_amount')
        )

        if not is_admin and user_id:
            total_query = total_query.filter(Invoice.uploaded_by_user_id == user_id)

        totals = total_query.first()

        # Handle case where user has no invoices
        if not totals or totals.total_count is None or totals.total_count == 0:
            return {
                'status_breakdown': {},
                'totals': {
                    'total_invoices': 0,
                    'total_amount': 0,
                    'average_invoice_value': 0
                }
            }

        # Format results
        status_breakdown = {}
        for status, count, amount in results:
            status_breakdown[status or 'unknown'] = {
                'count': count,
                'total_amount': float(amount) if amount else 0,
                'percentage': (count / totals.total_count * 100) if totals.total_count else 0
            }

        return {
            'status_breakdown': status_breakdown,
            'totals': {
                'total_invoices': totals.total_count or 0,
                'total_amount': float(totals.total_amount) if totals.total_amount else 0,
                'average_invoice_value': float(totals.avg_amount) if totals.avg_amount else 0
            }
        }

    def get_top_companies(self, user_id=None, is_admin=False, limit=10):
        """
        Get top companies by invoice count and revenue

        Args:
            user_id: User ID (if not admin, filters to user's invoices)
            is_admin: Whether the user is an admin
            limit: Number of companies to return

        Returns:
            dict with top companies by invoice count and by revenue
        """
        from app.models import Invoice, Company

        try:
            # Build base query
            base_query = self.db.query(
                Company.id,
                Company.company_name,
                Company.first_name,
                Company.last_name,
                func.count(Invoice.id).label('invoice_count'),
                func.sum(Invoice.total_amount).label('total_revenue'),
                func.avg(Invoice.total_amount).label('avg_invoice_value')
            ).join(
                Invoice, Company.id == Invoice.customer_id
            )

            # Filter by user if not admin
            if not is_admin and user_id:
                base_query = base_query.filter(Invoice.uploaded_by_user_id == user_id)

            base_query = base_query.group_by(Company.id, Company.company_name, Company.first_name, Company.last_name)

            # Top by invoice count
            top_by_count = base_query.order_by(func.count(Invoice.id).desc()).limit(limit).all()

            # Top by revenue
            top_by_revenue = base_query.order_by(func.sum(Invoice.total_amount).desc()).limit(limit).all()

            def format_company_data(results):
                if not results:
                    return []
                return [{
                    'id': str(company_id),
                'name': company_name or f"{first_name or ''} {last_name or ''}".strip() or 'Unknown',
                'invoice_count': invoice_count,
                'total_revenue': float(total_revenue) if total_revenue else 0,
                'avg_invoice_value': float(avg_invoice_value) if avg_invoice_value else 0
            } for company_id, company_name, first_name, last_name, invoice_count, total_revenue, avg_invoice_value in results]

            return {
                'top_by_invoice_count': format_company_data(top_by_count),
                'top_by_revenue': format_company_data(top_by_revenue)
            }
        except Exception as e:
            # Return empty results if there's an error (e.g., user has no invoices)
            return {
                'top_by_invoice_count': [],
                'top_by_revenue': []
            }

    def get_monthly_trends(self, user_id=None, is_admin=False, months=12):
        """
        Get monthly invoice and revenue trends

        Args:
            user_id: User ID (if not admin, filters to user's invoices)
            is_admin: Whether the user is an admin
            months: Number of months to look back

        Returns:
            dict with monthly trends data
        """
        from app.models import Invoice
        from datetime import datetime, timedelta

        try:
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=months * 30)

            # Build query
            query = self.db.query(
                extract('year', Invoice.invoice_date).label('year'),
                extract('month', Invoice.invoice_date).label('month'),
                func.count(Invoice.id).label('invoice_count'),
                func.sum(Invoice.total_amount).label('total_revenue'),
                func.avg(Invoice.total_amount).label('avg_invoice_value')
            ).filter(
                Invoice.invoice_date >= start_date,
                Invoice.invoice_date <= end_date
            )

            # Filter by user if not admin
            if not is_admin and user_id:
                query = query.filter(Invoice.uploaded_by_user_id == user_id)

            query = query.group_by('year', 'month').order_by('year', 'month')
            results = query.all()

            # Format results
            monthly_data = []
            for year, month, count, revenue, avg_value in results:
                monthly_data.append({
                    'year': int(year),
                    'month': int(month),
                    'month_label': f"{int(year)}-{int(month):02d}",
                    'invoice_count': count,
                    'total_revenue': float(revenue) if revenue else 0,
                    'avg_invoice_value': float(avg_value) if avg_value else 0
                })

            return {
                'monthly_trends': monthly_data,
                'date_range': {
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d')
                }
            }
        except Exception as e:
            # Return empty results if there's an error
            from datetime import datetime, timedelta
            end_date = datetime.now()
            start_date = end_date - timedelta(days=months * 30)
            return {
                'monthly_trends': [],
                'date_range': {
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d')
                }
            }

    def get_analytics_summary(self, user_id=None, is_admin=False):
        """
        Get comprehensive analytics summary combining all user-level reports

        Args:
            user_id: User ID (if not admin, filters to user's invoices)
            is_admin: Whether the user is an admin

        Returns:
            dict with all analytics data
        """
        invoice_stats = self.get_invoice_statistics(user_id, is_admin)
        top_companies = self.get_top_companies(user_id, is_admin, limit=10)
        monthly_trends = self.get_monthly_trends(user_id, is_admin, months=12)

        return {
            'invoice_statistics': invoice_stats,
            'top_companies': top_companies,
            'monthly_trends': monthly_trends
        }

    # ========================================
    # ADMIN-LEVEL ADVANCED ANALYTICS
    # ========================================

    def get_executive_dashboard(self):
        """
        Get executive dashboard metrics (admin only)

        Returns comprehensive KPIs for business overview
        """
        from app.models import Invoice, Company, User

        # Get date ranges
        current_year = datetime.now().year
        prev_year = current_year - 1
        current_month = datetime.now().month

        # Total revenue metrics
        total_revenue_query = self.db.query(
            func.sum(Invoice.total_amount).label('total_revenue'),
            func.count(Invoice.id).label('total_invoices'),
            func.avg(Invoice.total_amount).label('avg_invoice_value')
        ).first()

        # Year-over-year comparison
        current_year_revenue = self.db.query(
            func.sum(Invoice.total_amount)
        ).filter(
            extract('year', Invoice.invoice_date) == current_year
        ).scalar() or 0

        prev_year_revenue = self.db.query(
            func.sum(Invoice.total_amount)
        ).filter(
            extract('year', Invoice.invoice_date) == prev_year
        ).scalar() or 0

        yoy_growth = ((current_year_revenue - prev_year_revenue) / prev_year_revenue * 100) if prev_year_revenue > 0 else 0

        # Customer metrics
        total_customers = self.db.query(func.count(func.distinct(Company.id))).scalar() or 0
        total_users = self.db.query(func.count(User.id)).scalar() or 0

        # Payment status breakdown
        payment_status = self.db.query(
            Invoice.payment_status,
            func.count(Invoice.id).label('count'),
            func.sum(Invoice.total_amount).label('amount')
        ).group_by(Invoice.payment_status).all()

        status_breakdown = {}
        for status, count, amount in payment_status:
            status_breakdown[status or 'unknown'] = {
                'count': count,
                'amount': float(amount) if amount else 0
            }

        return {
            'financial_metrics': {
                'total_revenue': float(total_revenue_query.total_revenue or 0),
                'total_invoices': total_revenue_query.total_invoices or 0,
                'avg_invoice_value': float(total_revenue_query.avg_invoice_value or 0),
                'yoy_growth': float(yoy_growth)
            },
            'operational_metrics': {
                'total_customers': total_customers,
                'total_users': total_users,
                'revenue_per_customer': float(total_revenue_query.total_revenue / total_customers) if total_customers > 0 else 0
            },
            'payment_status': status_breakdown
        }

    def get_customer_analytics(self, limit=20):
        """
        Get customer value analysis (admin only)

        Returns top customers by revenue, order frequency, and lifetime value
        """
        from app.models import Invoice, Company

        # Top customers by revenue
        top_customers = self.db.query(
            Company.id,
            Company.company_name,
            Company.first_name,
            Company.last_name,
            func.count(Invoice.id).label('order_count'),
            func.sum(Invoice.total_amount).label('total_revenue'),
            func.avg(Invoice.total_amount).label('avg_order_value'),
            func.min(Invoice.invoice_date).label('first_order'),
            func.max(Invoice.invoice_date).label('last_order')
        ).join(
            Invoice, Company.id == Invoice.customer_id
        ).group_by(
            Company.id, Company.company_name, Company.first_name, Company.last_name
        ).order_by(
            func.sum(Invoice.total_amount).desc()
        ).limit(limit).all()

        customers_data = []
        for company_id, company_name, first_name, last_name, order_count, total_revenue, avg_order, first_order, last_order in top_customers:
            # Calculate customer lifetime (days)
            if first_order and last_order:
                lifetime_days = (last_order - first_order).days + 1
            else:
                lifetime_days = 0

            customers_data.append({
                'id': str(company_id),
                'name': company_name or f"{first_name or ''} {last_name or ''}".strip() or 'Unknown',
                'order_count': order_count,
                'total_revenue': float(total_revenue) if total_revenue else 0,
                'avg_order_value': float(avg_order) if avg_order else 0,
                'lifetime_days': lifetime_days,
                'first_order': first_order.strftime('%Y-%m-%d') if first_order else None,
                'last_order': last_order.strftime('%Y-%m-%d') if last_order else None
            })

        return {
            'top_customers': customers_data,
            'total_analyzed': len(customers_data)
        }

    def get_product_performance(self, limit=20):
        """
        Get product performance analysis (admin only)

        Returns top/bottom products by revenue and profit margins
        """
        from app.models import Invoice, InvoiceLineItem, Product

        # Product performance
        product_stats = self.db.query(
            Product.id,
            Product.name,
            Product.standard_cost,
            Product.list_price,
            func.sum(InvoiceLineItem.quantity).label('total_quantity'),
            func.sum(InvoiceLineItem.line_total).label('total_revenue'),
            func.avg(InvoiceLineItem.unit_price).label('avg_selling_price')
        ).join(
            InvoiceLineItem, Product.id == InvoiceLineItem.product_id
        ).group_by(
            Product.id, Product.name, Product.standard_cost, Product.list_price
        ).order_by(
            func.sum(InvoiceLineItem.line_total).desc()
        ).limit(limit).all()

        products_data = []
        for product_id, name, standard_cost, list_price, quantity, revenue, avg_price in product_stats:
            # Calculate profit margin
            cost = standard_cost or 0
            price = avg_price or list_price or 0
            margin = ((price - cost) / price * 100) if price > 0 else 0

            products_data.append({
                'id': str(product_id),
                'name': name,
                'total_quantity': quantity,
                'total_revenue': float(revenue) if revenue else 0,
                'avg_selling_price': float(avg_price) if avg_price else 0,
                'standard_cost': float(cost),
                'profit_margin': float(margin)
            })

        return {
            'top_products': products_data,
            'total_analyzed': len(products_data)
        }

    # ========================================
    # ADVANCED ANALYSIS REPORTS (Image Generation)
    # ========================================

    def generate_business_intelligence_report(self, params):
        """
        Generate comprehensive business intelligence analysis with multiple visualizations
        Adapted from data_analysis.py discovery script

        Args:
            params: dict with date_range filters

        Returns:
            dict with file_path, metrics, and list of generated images
        """
        import matplotlib.pyplot as plt
        import seaborn as sns
        from matplotlib.ticker import FuncFormatter

        def currency_formatter(x, p):
            """Format numbers as currency"""
            if abs(x) >= 1e6:
                return f'${x/1e6:.1f}M'
            elif abs(x) >= 1e3:
                return f'${x/1e3:.0f}K'
            else:
                return f'${x:.0f}'

        from app.models import (
            Invoice, InvoiceLineItem, Product,
            ProductCategory, ProductSubCategory,
            Company, SalesTerritory
        )

        # Build comprehensive query
        query = self.db.query(
            InvoiceLineItem.quantity,
            InvoiceLineItem.unit_price,
            InvoiceLineItem.line_total,
            Product.name.label('product_name'),
            Product.standard_cost,
            Product.list_price,
            ProductSubCategory.name.label('subcategory_name'),
            ProductCategory.name.label('category_name'),
            Invoice.invoice_date,
            Invoice.customer_id,
            Invoice.territory_id,
            Invoice.sales_order_id
        ).join(
            Invoice, InvoiceLineItem.invoice_id == Invoice.id
        ).join(
            Product, InvoiceLineItem.product_id == Product.id
        ).join(
            ProductSubCategory, Product.subcategory_id == ProductSubCategory.subcategory_id
        ).join(
            ProductCategory, ProductSubCategory.category_id == ProductCategory.category_id
        )

        # Apply date filters
        if params.get('start_date'):
            query = query.filter(Invoice.invoice_date >= params['start_date'])
        if params.get('end_date'):
            query = query.filter(Invoice.invoice_date <= params['end_date'])

        # Execute and load into DataFrame
        df = pd.read_sql(query.statement, self.db.bind)

        if df.empty:
            return {'error': 'No data found for the specified filters'}

        # Calculate business metrics
        df['revenue'] = df['line_total']
        df['cost'] = df['quantity'] * df['standard_cost']
        df['profit'] = df['revenue'] - df['cost']
        df['profit_margin'] = (df['profit'] / df['revenue']) * 100
        df['invoice_date'] = pd.to_datetime(df['invoice_date'])

        # Clean data
        df['cost'] = df['cost'].fillna(0)
        df['profit'] = df['profit'].fillna(df['revenue'])
        df['profit_margin'] = df['profit_margin'].fillna(0)

        # Create Sales Performance Analysis
        fig, axes = plt.subplots(2, 2, figsize=(20, 16))
        fig.suptitle('Sales Performance Analysis', fontsize=20, fontweight='bold')

        # 1. Monthly Revenue and Profit Trends
        monthly_revenue = df.groupby(df['invoice_date'].dt.to_period('M')).agg({
            'revenue': 'sum',
            'profit': 'sum',
            'quantity': 'sum'
        }).reset_index()
        monthly_revenue['invoice_date'] = monthly_revenue['invoice_date'].dt.to_timestamp()

        ax1 = axes[0, 0]
        ax1.plot(monthly_revenue['invoice_date'], monthly_revenue['revenue'],
                 linewidth=3, marker='o', markersize=8, color='#2E86C1', label='Revenue')
        ax1.plot(monthly_revenue['invoice_date'], monthly_revenue['profit'],
                 linewidth=3, marker='s', markersize=6, color='#28B463', label='Profit')
        ax1.set_title('Monthly Revenue & Profit Trends', fontsize=16, fontweight='bold')
        ax1.set_xlabel('Date', fontsize=12)
        ax1.set_ylabel('Amount ($)', fontsize=12)
        ax1.yaxis.set_major_formatter(FuncFormatter(currency_formatter))
        ax1.legend(fontsize=12)
        ax1.grid(True, alpha=0.3)

        # 2. Revenue by Product Category
        category_performance = df.groupby('category_name').agg({
            'revenue': 'sum',
            'profit': 'sum',
            'quantity': 'sum'
        }).sort_values('revenue', ascending=False)

        ax2 = axes[0, 1]
        bars = ax2.bar(category_performance.index, category_performance['revenue'],
                       color=['#E74C3C', '#3498DB', '#F39C12', '#9B59B6'][:len(category_performance)])
        ax2.set_title('Revenue by Product Category', fontsize=16, fontweight='bold')
        ax2.set_ylabel('Revenue ($)', fontsize=12)
        ax2.yaxis.set_major_formatter(FuncFormatter(currency_formatter))
        ax2.tick_params(axis='x', rotation=45)

        # 3. Profit Margins by Category
        category_margins = df.groupby('category_name').agg({
            'profit_margin': 'mean',
            'revenue': 'sum'
        }).sort_values('profit_margin', ascending=True)

        ax3 = axes[1, 0]
        colors = ['#E74C3C' if x < 30 else '#F39C12' if x < 50 else '#27AE60'
                  for x in category_margins['profit_margin']]
        bars = ax3.barh(category_margins.index, category_margins['profit_margin'], color=colors)
        ax3.set_title('Average Profit Margin by Category', fontsize=16, fontweight='bold')
        ax3.set_xlabel('Profit Margin (%)', fontsize=12)

        # 4. Product Performance Matrix
        product_performance = df.groupby('product_name').agg({
            'quantity': 'sum',
            'profit': 'sum',
            'revenue': 'sum',
            'profit_margin': 'mean'
        }).reset_index()

        ax4 = axes[1, 1]
        scatter = ax4.scatter(product_performance['quantity'], product_performance['profit'],
                             s=product_performance['revenue']/1000, alpha=0.6,
                             c=product_performance['profit_margin'], cmap='RdYlGn')
        ax4.set_title('Product Performance Matrix\n(Size = Revenue, Color = Profit Margin)',
                      fontsize=16, fontweight='bold')
        ax4.set_xlabel('Total Quantity Sold', fontsize=12)
        ax4.set_ylabel('Total Profit ($)', fontsize=12)
        ax4.yaxis.set_major_formatter(FuncFormatter(currency_formatter))
        plt.colorbar(scatter, ax=ax4, label='Profit Margin (%)')

        plt.tight_layout()

        # Save sales analysis
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        sales_filename = f'business_sales_analysis_{timestamp}.png'
        sales_path = self.output_dir / sales_filename
        plt.savefig(sales_path, dpi=300, bbox_inches='tight')
        plt.close()

        # Create Operational Insights Dashboard
        operational_path = self._create_operational_insights(df, timestamp)

        # Calculate executive summary metrics
        total_revenue = df['revenue'].sum()
        total_profit = df['profit'].sum()
        overall_margin = (total_profit / total_revenue) * 100 if total_revenue > 0 else 0
        total_customers = df['customer_id'].nunique()
        total_orders = df['sales_order_id'].nunique()
        avg_order_value = total_revenue / total_orders if total_orders > 0 else 0

        # Calculate growth metrics
        current_year = df['invoice_date'].dt.year.max()
        prev_year = current_year - 1
        current_year_revenue = df[df['invoice_date'].dt.year == current_year]['revenue'].sum()
        prev_year_revenue = df[df['invoice_date'].dt.year == prev_year]['revenue'].sum()
        yoy_growth = ((current_year_revenue - prev_year_revenue) / prev_year_revenue) * 100 if prev_year_revenue > 0 else 0

        return {
            'file_path': str(sales_path),
            'filename': sales_filename,
            'additional_files': [
                {'path': str(operational_path), 'name': operational_path.name}
            ],
            'metrics': {
                'financial': {
                    'total_revenue': float(total_revenue),
                    'total_profit': float(total_profit),
                    'overall_margin': float(overall_margin),
                    'yoy_growth': float(yoy_growth)
                },
                'operational': {
                    'total_customers': int(total_customers),
                    'total_orders': int(total_orders),
                    'avg_order_value': float(avg_order_value),
                    'revenue_per_customer': float(total_revenue/total_customers) if total_customers > 0 else 0
                },
                'categories_analyzed': len(category_performance),
                'products_analyzed': len(product_performance),
                'date_range': {
                    'start': params.get('start_date'),
                    'end': params.get('end_date')
                }
            }
        }

    def _create_operational_insights(self, df, timestamp):
        """Create operational performance insights dashboard"""
        import matplotlib.pyplot as plt
        from matplotlib.ticker import FuncFormatter

        def currency_formatter(x, p):
            if abs(x) >= 1e6:
                return f'${x/1e6:.1f}M'
            elif abs(x) >= 1e3:
                return f'${x/1e3:.0f}K'
            else:
                return f'${x:.0f}'

        fig, axes = plt.subplots(2, 2, figsize=(20, 16))
        fig.suptitle('Operational Performance & Customer Insights', fontsize=20, fontweight='bold')

        # 1. Sales Performance by Territory
        if 'territory_id' in df.columns and df['territory_id'].notna().any():
            territory_performance = df.groupby('territory_id').agg({
                'revenue': 'sum',
                'profit': 'sum',
                'quantity': 'sum',
                'sales_order_id': 'nunique'
            }).sort_values('revenue', ascending=False)

            ax1 = axes[0, 0]
            bars = ax1.bar(territory_performance.index.astype(str), territory_performance['revenue'],
                           color=plt.cm.Set3(np.linspace(0, 1, len(territory_performance))))
            ax1.set_title('Revenue by Sales Territory', fontsize=16, fontweight='bold')
            ax1.set_xlabel('Territory ID', fontsize=12)
            ax1.set_ylabel('Revenue ($)', fontsize=12)
            ax1.yaxis.set_major_formatter(FuncFormatter(currency_formatter))

            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax1.text(bar.get_x() + bar.get_width()/2., height + height*0.01,
                            f'${height/1e6:.1f}M', ha='center', va='bottom', fontsize=10, fontweight='bold')
        else:
            ax1 = axes[0, 0]
            ax1.text(0.5, 0.5, 'No Territory Data Available',
                    ha='center', va='center', fontsize=14)
            ax1.set_xlim(0, 1)
            ax1.set_ylim(0, 1)

        # 2. Customer Value Analysis
        customer_value = df.groupby('customer_id').agg({
            'revenue': 'sum',
            'profit': 'sum',
            'sales_order_id': 'nunique'
        }).sort_values('revenue', ascending=False).head(20)

        ax2 = axes[0, 1]
        scatter = ax2.scatter(customer_value['sales_order_id'], customer_value['revenue'],
                             s=customer_value['profit']/100, alpha=0.6,
                             c=customer_value['profit'], cmap='viridis')
        ax2.set_title('Top 20 Customer Value Analysis\n(Size & Color = Profit)',
                      fontsize=16, fontweight='bold')
        ax2.set_xlabel('Number of Orders', fontsize=12)
        ax2.set_ylabel('Total Revenue ($)', fontsize=12)
        ax2.yaxis.set_major_formatter(FuncFormatter(currency_formatter))

        # 3. Seasonal Sales Pattern
        df['month'] = df['invoice_date'].dt.month
        monthly_pattern = df.groupby('month').agg({
            'revenue': 'sum',
            'quantity': 'sum'
        })

        ax3 = axes[1, 0]
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        bars = ax3.bar(months, monthly_pattern['revenue'],
                       color=plt.cm.coolwarm(monthly_pattern['revenue'] / monthly_pattern['revenue'].max()))
        ax3.set_title('Seasonal Sales Pattern', fontsize=16, fontweight='bold')
        ax3.set_ylabel('Revenue ($)', fontsize=12)
        ax3.yaxis.set_major_formatter(FuncFormatter(currency_formatter))
        plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45)

        # 4. Product Category Lifecycle
        if 'category_name' in df.columns:
            product_lifecycle = df.groupby([df['invoice_date'].dt.to_period('M'), 'category_name']).agg({
                'revenue': 'sum'
            }).reset_index()
            product_lifecycle['invoice_date'] = product_lifecycle['invoice_date'].dt.to_timestamp()

            ax4 = axes[1, 1]
            categories = product_lifecycle['category_name'].unique()
            colors = plt.cm.Set1(np.linspace(0, 1, len(categories)))

            for i, category in enumerate(categories):
                cat_data = product_lifecycle[product_lifecycle['category_name'] == category]
                monthly_cat = cat_data.groupby('invoice_date')['revenue'].sum()
                ax4.plot(monthly_cat.index, monthly_cat.values,
                        linewidth=3, marker='o', label=category, color=colors[i])

            ax4.set_title('Product Category Lifecycle', fontsize=16, fontweight='bold')
            ax4.set_xlabel('Date', fontsize=12)
            ax4.set_ylabel('Revenue ($)', fontsize=12)
            ax4.yaxis.set_major_formatter(FuncFormatter(currency_formatter))
            ax4.legend(fontsize=10)
            ax4.grid(True, alpha=0.3)

        plt.tight_layout()
        operational_filename = f'operational_insights_{timestamp}.png'
        operational_path = self.output_dir / operational_filename
        plt.savefig(operational_path, dpi=300, bbox_inches='tight')
        plt.close()

        return operational_path

    def generate_profit_margin_analysis(self, params):
        """
        Generate detailed profit margin and break-even analysis
        Adapted from profit_analysis.py discovery script

        Args:
            params: dict with date_range and category filters

        Returns:
            dict with file_path and comprehensive profit metrics
        """
        import matplotlib.pyplot as plt
        import seaborn as sns
        from matplotlib.ticker import FuncFormatter

        def currency_formatter(x, p):
            if abs(x) >= 1e6:
                return f'${x/1e6:.1f}M'
            elif abs(x) >= 1e3:
                return f'${x/1e3:.0f}K'
            else:
                return f'${x:.0f}'

        from app.models import (
            Invoice, InvoiceLineItem, Product,
            ProductCategory, ProductSubCategory
        )

        # Build query
        query = self.db.query(
            InvoiceLineItem.quantity,
            InvoiceLineItem.unit_price,
            InvoiceLineItem.line_total,
            Product.id.label('product_id'),
            Product.name.label('product_name'),
            Product.standard_cost,
            Product.list_price,
            ProductCategory.name.label('category_name'),
            Invoice.invoice_date
        ).join(
            Invoice, InvoiceLineItem.invoice_id == Invoice.id
        ).join(
            Product, InvoiceLineItem.product_id == Product.id
        ).join(
            ProductSubCategory, Product.subcategory_id == ProductSubCategory.subcategory_id
        ).join(
            ProductCategory, ProductSubCategory.category_id == ProductCategory.category_id
        )

        # Apply filters
        if params.get('start_date'):
            query = query.filter(Invoice.invoice_date >= params['start_date'])
        if params.get('end_date'):
            query = query.filter(Invoice.invoice_date <= params['end_date'])

        # Execute and load
        df = pd.read_sql(query.statement, self.db.bind)

        if df.empty:
            return {'error': 'No data found for the specified filters'}

        # Calculate profit metrics
        df['actual_unit_cost'] = df['standard_cost']
        df['actual_unit_price'] = df['unit_price']
        df['unit_profit_margin'] = df['actual_unit_price'] - df['actual_unit_cost']
        df['profit_margin_percent'] = (df['unit_profit_margin'] / df['actual_unit_price']) * 100
        df['total_revenue'] = df['line_total']
        df['total_cost'] = df['quantity'] * df['actual_unit_cost']
        df['total_profit'] = df['total_revenue'] - df['total_cost']

        # Clean data
        clean_data = df.dropna(subset=['actual_unit_cost', 'actual_unit_price'])
        clean_data = clean_data[clean_data['actual_unit_cost'] > 0]
        clean_data = clean_data[clean_data['actual_unit_price'] > 0]

        # Create comprehensive analysis
        fig, axes = plt.subplots(2, 2, figsize=(20, 16))
        fig.suptitle('Profit Margin & Break-Even Analysis\nRaw Material Costs vs Customer Pricing',
                     fontsize=18, fontweight='bold')

        # 1. Cost vs Selling Price Scatter
        ax1 = axes[0, 0]
        product_summary = clean_data.groupby(['product_id', 'product_name', 'category_name']).agg({
            'actual_unit_cost': 'mean',
            'actual_unit_price': 'mean',
            'quantity': 'sum',
            'total_profit': 'sum'
        }).reset_index()

        categories_list = product_summary['category_name'].unique()
        colors = plt.cm.Set1(np.linspace(0, 1, len(categories_list)))
        category_colors = dict(zip(categories_list, colors))

        for category in categories_list:
            cat_data = product_summary[product_summary['category_name'] == category]
            scatter = ax1.scatter(cat_data['actual_unit_cost'], cat_data['actual_unit_price'],
                                 s=cat_data['quantity']/10, alpha=0.7,
                                 c=[category_colors[category]], label=category)

        # Add break-even line
        max_val = max(product_summary['actual_unit_price'].max(), product_summary['actual_unit_cost'].max())
        ax1.plot([0, max_val], [0, max_val], 'r--', linewidth=2, label='Break-Even Line', alpha=0.8)

        ax1.set_title('Raw Material Cost vs Customer Selling Price\n(Size = Sales Volume)',
                      fontsize=14, fontweight='bold')
        ax1.set_xlabel('Raw Material Cost ($)', fontsize=12)
        ax1.set_ylabel('Customer Selling Price ($)', fontsize=12)
        ax1.legend(fontsize=10)
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_formatter(FuncFormatter(currency_formatter))
        ax1.yaxis.set_major_formatter(FuncFormatter(currency_formatter))

        # 2. Profit Margin by Category
        ax2 = axes[0, 1]
        category_margins = clean_data.groupby('category_name').agg({
            'profit_margin_percent': 'mean',
            'total_revenue': 'sum',
            'total_profit': 'sum'
        }).sort_values('profit_margin_percent', ascending=True)

        bars = ax2.barh(category_margins.index, category_margins['profit_margin_percent'],
                        color=['#E74C3C' if x < 20 else '#F39C12' if x < 40 else '#27AE60'
                              for x in category_margins['profit_margin_percent']])

        ax2.set_title('Profit Margin % by Product Category\n(Red < 20%, Yellow < 40%, Green >= 40%)',
                      fontsize=14, fontweight='bold')
        ax2.set_xlabel('Average Profit Margin (%)', fontsize=12)

        for i, (bar, margin) in enumerate(zip(bars, category_margins['profit_margin_percent'])):
            ax2.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
                    f'{margin:.1f}%', va='center', fontsize=12, fontweight='bold')

        # 3. Break-Even Analysis
        ax3 = axes[1, 0]
        fixed_cost_per_product = 50000  # Assumed fixed costs
        product_breakeven = product_summary.copy()
        product_breakeven['unit_profit'] = product_breakeven['actual_unit_price'] - product_breakeven['actual_unit_cost']
        product_breakeven['breakeven_units'] = fixed_cost_per_product / product_breakeven['unit_profit']

        realistic_breakeven = product_breakeven[
            (product_breakeven['breakeven_units'] > 0) &
            (product_breakeven['breakeven_units'] < 10000)
        ].nsmallest(15, 'breakeven_units')

        bars = ax3.bar(range(len(realistic_breakeven)), realistic_breakeven['breakeven_units'],
                       color=plt.cm.viridis(np.linspace(0, 1, len(realistic_breakeven))))

        ax3.set_title('Break-Even Analysis: Units to Sell\n(Assuming $50K Fixed Costs per Product)',
                      fontsize=14, fontweight='bold')
        ax3.set_ylabel('Break-Even Quantity (Units)', fontsize=12)
        ax3.set_xticks(range(len(realistic_breakeven)))
        ax3.set_xticklabels([name[:20] + '...' if len(name) > 20 else name
                            for name in realistic_breakeven['product_name']],
                           rotation=45, ha='right', fontsize=9)

        for i, (bar, units) in enumerate(zip(bars, realistic_breakeven['breakeven_units'])):
            ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + bar.get_height()*0.01,
                    f'{units:.0f}', ha='center', va='bottom', fontsize=10, fontweight='bold')

        # 4. Cost Structure Analysis
        ax4 = axes[1, 1]
        category_economics = clean_data.groupby('category_name').agg({
            'total_cost': 'sum',
            'total_revenue': 'sum',
            'total_profit': 'sum'
        })

        category_economics['cost_ratio'] = category_economics['total_cost'] / category_economics['total_revenue']
        category_economics['profit_ratio'] = category_economics['total_profit'] / category_economics['total_revenue']

        categories_sorted = category_economics.sort_values('total_revenue', ascending=False).index
        x_pos = np.arange(len(categories_sorted))

        cost_bars = ax4.bar(x_pos, category_economics.loc[categories_sorted, 'cost_ratio'] * 100,
                           label='Raw Material Cost %', color='#E74C3C', alpha=0.8)
        profit_bars = ax4.bar(x_pos, category_economics.loc[categories_sorted, 'profit_ratio'] * 100,
                             bottom=category_economics.loc[categories_sorted, 'cost_ratio'] * 100,
                             label='Profit %', color='#27AE60', alpha=0.8)

        ax4.set_title('Cost Structure: Where Does Revenue Go?\n(Cost % vs Profit %)',
                      fontsize=14, fontweight='bold')
        ax4.set_xlabel('Product Categories', fontsize=12)
        ax4.set_ylabel('Percentage of Revenue (%)', fontsize=12)
        ax4.set_xticks(x_pos)
        ax4.set_xticklabels(categories_sorted, rotation=45, ha='right')
        ax4.legend(fontsize=12)
        ax4.set_ylim(0, 100)

        for i, category in enumerate(categories_sorted):
            cost_pct = category_economics.loc[category, 'cost_ratio'] * 100
            profit_pct = category_economics.loc[category, 'profit_ratio'] * 100
            ax4.text(i, cost_pct/2, f'{cost_pct:.1f}%', ha='center', va='center',
                    fontweight='bold', color='white')
            ax4.text(i, cost_pct + profit_pct/2, f'{profit_pct:.1f}%', ha='center', va='center',
                    fontweight='bold', color='white')

        plt.tight_layout()

        # Save report
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'profit_margin_analysis_{timestamp}.png'
        file_path = self.output_dir / filename
        plt.savefig(file_path, dpi=300, bbox_inches='tight')
        plt.close()

        # Calculate key insights
        total_revenue = clean_data['total_revenue'].sum()
        total_cost = clean_data['total_cost'].sum()
        total_profit = clean_data['total_profit'].sum()
        overall_margin = (total_profit / total_revenue) * 100 if total_revenue > 0 else 0

        return {
            'file_path': str(file_path),
            'filename': filename,
            'metrics': {
                'overall_performance': {
                    'total_revenue': float(total_revenue),
                    'total_cost': float(total_cost),
                    'total_profit': float(total_profit),
                    'overall_margin': float(overall_margin)
                },
                'category_analysis': {
                    'best_margin': {
                        'category': category_margins.index[-1],
                        'margin': float(category_margins['profit_margin_percent'].iloc[-1])
                    },
                    'worst_margin': {
                        'category': category_margins.index[0],
                        'margin': float(category_margins['profit_margin_percent'].iloc[0])
                    }
                },
                'products_analyzed': len(product_summary),
                'categories_analyzed': len(category_margins),
                'date_range': {
                    'start': params.get('start_date'),
                    'end': params.get('end_date')
                }
            }
        }
