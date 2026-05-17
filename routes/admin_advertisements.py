from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from database import db, SellerAdvertisement, User, Product, seller_advertisement_image_abs_path, clear_seller_advertisement_fk_before_delete
import os

admin_ad_bp = Blueprint('admin_ad', __name__)

@admin_ad_bp.route('/admin/seller-advertisements')
def list_seller_advertisements():
    """List all seller advertisements for admin review"""
    if not session.get('user_id') or session.get('user_type') != 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    # Get all seller advertisements with seller and product info
    advertisements = db.session.query(SellerAdvertisement, User, Product).join(
        User, SellerAdvertisement.seller_id == User.id
    ).join(
        Product, SellerAdvertisement.product_id == Product.id
    ).order_by(SellerAdvertisement.created_at.desc()).all()
    
    return render_template('admin/seller_advertisements.html', advertisements=advertisements)

@admin_ad_bp.route('/admin/seller-advertisements/<int:ad_id>/approve', methods=['POST'])
def approve_advertisement(ad_id):
    """Approve a seller advertisement"""
    if not session.get('user_id') or session.get('user_type') != 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    advertisement = SellerAdvertisement.query.get_or_404(ad_id)
    advertisement.is_approved = True
    db.session.commit()
    
    flash(f'Advertisement "{advertisement.title}" has been approved!', 'success')
    return redirect(url_for('admin_ad.list_seller_advertisements'))

@admin_ad_bp.route('/admin/seller-advertisements/<int:ad_id>/reject', methods=['POST'])
def reject_advertisement(ad_id):
    """Reject a seller advertisement"""
    if not session.get('user_id') or session.get('user_type') != 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    advertisement = SellerAdvertisement.query.get_or_404(ad_id)
    advertisement.is_approved = False
    advertisement.is_active = False
    db.session.commit()
    
    flash(f'Advertisement "{advertisement.title}" has been rejected!', 'warning')
    return redirect(url_for('admin_ad.list_seller_advertisements'))

@admin_ad_bp.route('/admin/seller-advertisements/<int:ad_id>/delete', methods=['POST'])
def delete_advertisement(ad_id):
    """Delete a seller advertisement"""
    if not session.get('user_id') or session.get('user_type') != 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    advertisement = SellerAdvertisement.query.get_or_404(ad_id)
    title = advertisement.title
    
    # Delete image file if exists
    if advertisement.image_url:
        image_path = seller_advertisement_image_abs_path(advertisement.image_url)
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except OSError:
                pass
    
    clear_seller_advertisement_fk_before_delete(advertisement.id)

    db.session.delete(advertisement)
    db.session.commit()
    
    flash(f'Advertisement "{title}" has been deleted!', 'success')
    return redirect(url_for('admin_ad.list_seller_advertisements'))

@admin_ad_bp.route('/admin/seller-advertisements/<int:ad_id>/toggle', methods=['POST'])
def toggle_advertisement(ad_id):
    """Toggle advertisement active status"""
    if not session.get('user_id') or session.get('user_type') != 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    advertisement = SellerAdvertisement.query.get_or_404(ad_id)
    advertisement.is_active = not advertisement.is_active
    db.session.commit()
    
    status = 'activated' if advertisement.is_active else 'deactivated'
    flash(f'Advertisement "{advertisement.title}" has been {status}!', 'success')
    return redirect(url_for('admin_ad.list_seller_advertisements'))
