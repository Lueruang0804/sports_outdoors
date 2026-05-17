from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from database import (
    db,
    User,
    Product,
    SellerAdvertisement,
    apply_seller_ad_to_buyer_cart_items,
    seller_advertisement_image_abs_path,
    clear_seller_advertisement_fk_before_delete,
)
from datetime import datetime
from timezone_utils import parse_ph_datetime, ph_to_utc, is_advertisement_visible, isoformat_utc_z
import os

seller_ad_bp = Blueprint('seller_ad', __name__)

@seller_ad_bp.route('/seller/advertisements')
def list_advertisements():
    """List all seller advertisements"""
    if not session.get('user_id') or session.get('user_type') != 'seller':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    seller_id = session['user_id']
    advertisements = SellerAdvertisement.query.filter_by(seller_id=seller_id).order_by(SellerAdvertisement.created_at.desc()).all()
    
    return render_template('seller/advertisements.html', advertisements=advertisements)

@seller_ad_bp.route('/seller/advertisements/create', methods=['GET', 'POST'])
def create_advertisement():
    """Create new advertisement"""
    if not session.get('user_id') or session.get('user_type') != 'seller':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    seller_id = session['user_id']
    
    if request.method == 'POST':
        product_id = request.form['product_id']
        title = request.form['title']
        description = request.form['description']
        discount_percentage = int(request.form['discount_percentage'])
        promo_message = request.form.get('promo_message', '')
        # Parse datetime inputs as Philippine time and convert to UTC for storage
        starts_at_ph = parse_ph_datetime(request.form['starts_at'])
        expires_at_ph = parse_ph_datetime(request.form['expires_at'])
        starts_at = ph_to_utc(starts_at_ph)
        expires_at = ph_to_utc(expires_at_ph)

        if expires_at <= starts_at:
            flash('End date/time must be after the start date/time.', 'error')
            return redirect(url_for('seller_ad.create_advertisement'))
        
        # Get product details
        product = Product.query.get(product_id)
        if not product or product.seller_id != seller_id:
            flash('Invalid product selected.', 'error')
            return redirect(url_for('seller_ad.create_advertisement'))
        
        # Calculate discounted price
        original_price = float(product.price)
        discounted_price = original_price * (1 - discount_percentage / 100)
        
        # Handle image upload
        image_url = None
        if 'advertisement_image' in request.files:
            file = request.files['advertisement_image']
            if file and file.filename:
                filename = secure_filename(file.filename)
                timestamp = str(int(datetime.utcnow().timestamp()))
                filename = f"{timestamp}_{filename}"
                os.makedirs(os.path.join('static/uploads/advertisements'), exist_ok=True)
                file.save(os.path.join('static/uploads/advertisements', filename))
                image_url = f"uploads/advertisements/{filename}"
        
        # Create advertisement
        advertisement = SellerAdvertisement(
            seller_id=seller_id,
            product_id=product_id,
            title=title,
            description=description,
            discount_percentage=discount_percentage,
            original_price=original_price,
            discounted_price=discounted_price,
            image_url=image_url,
            promo_message=promo_message,
            starts_at=starts_at,
            expires_at=expires_at
        )
        
        db.session.add(advertisement)
        db.session.commit()
        
        flash('Advertisement created successfully! Pending admin approval.', 'success')
        return redirect(url_for('seller_ad.list_advertisements'))
    
    # Get seller's products for dropdown
    products = Product.query.filter_by(seller_id=seller_id, status='active').all()
    
    return render_template('seller/create_advertisement.html', products=products)

@seller_ad_bp.route('/seller/advertisements/<int:ad_id>/edit', methods=['GET', 'POST'])
def edit_advertisement(ad_id):
    """Edit advertisement"""
    if not session.get('user_id') or session.get('user_type') != 'seller':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    seller_id = session['user_id']
    advertisement = SellerAdvertisement.query.filter_by(id=ad_id, seller_id=seller_id).first()
    
    if not advertisement:
        flash('Advertisement not found.', 'error')
        return redirect(url_for('seller_ad.list_advertisements'))
    
    if request.method == 'POST':
        advertisement.title = request.form['title']
        advertisement.description = request.form['description']
        advertisement.discount_percentage = int(request.form['discount_percentage'])
        advertisement.promo_message = request.form.get('promo_message', '')
        # Parse datetime inputs as Philippine time and convert to UTC for storage
        starts_at_ph = parse_ph_datetime(request.form['starts_at'])
        expires_at_ph = parse_ph_datetime(request.form['expires_at'])
        advertisement.starts_at = ph_to_utc(starts_at_ph)
        advertisement.expires_at = ph_to_utc(expires_at_ph)

        if advertisement.expires_at <= advertisement.starts_at:
            flash('End date/time must be after the start date/time.', 'error')
            return redirect(url_for('seller_ad.edit_advertisement', ad_id=ad_id))
        
        # Recalculate discounted price from current product list price
        product = Product.query.get(advertisement.product_id)
        if product:
            advertisement.original_price = float(product.price)
        advertisement.discounted_price = float(advertisement.original_price) * (1 - advertisement.discount_percentage / 100)
        
        # Handle new image upload
        if 'advertisement_image' in request.files:
            file = request.files['advertisement_image']
            if file and file.filename:
                filename = secure_filename(file.filename)
                timestamp = str(int(datetime.utcnow().timestamp()))
                filename = f"{timestamp}_{filename}"
                os.makedirs(os.path.join('static/uploads/advertisements'), exist_ok=True)
                file.save(os.path.join('static/uploads/advertisements', filename))
                advertisement.image_url = f"uploads/advertisements/{filename}"
        
        db.session.commit()
        flash('Advertisement updated successfully!', 'success')
        return redirect(url_for('seller_ad.list_advertisements'))
    
    products = Product.query.filter_by(seller_id=seller_id, status='active').all()
    return render_template('seller/edit_advertisement.html', advertisement=advertisement, products=products)

@seller_ad_bp.route('/seller/advertisements/<int:ad_id>/delete', methods=['POST'])
def delete_advertisement(ad_id):
    """Delete advertisement"""
    if not session.get('user_id') or session.get('user_type') != 'seller':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    seller_id = session['user_id']
    advertisement = SellerAdvertisement.query.filter_by(id=ad_id, seller_id=seller_id).first()
    
    if not advertisement:
        flash('Advertisement not found.', 'error')
        return redirect(url_for('seller_ad.list_advertisements'))
    
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
    
    flash('Advertisement deleted successfully!', 'success')
    return redirect(url_for('seller_ad.list_advertisements'))

@seller_ad_bp.route('/seller/advertisements/<int:ad_id>/toggle', methods=['POST'])
def toggle_advertisement(ad_id):
    """Toggle advertisement active status"""
    if not session.get('user_id') or session.get('user_type') != 'seller':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    seller_id = session['user_id']
    advertisement = SellerAdvertisement.query.filter_by(id=ad_id, seller_id=seller_id).first()
    
    if not advertisement:
        flash('Advertisement not found.', 'error')
        return redirect(url_for('seller_ad.list_advertisements'))
    
    advertisement.is_active = not advertisement.is_active
    db.session.commit()
    
    status = 'activated' if advertisement.is_active else 'deactivated'
    flash(f'Advertisement {status} successfully!', 'success')
    return redirect(url_for('seller_ad.list_advertisements'))

@seller_ad_bp.route('/advertisement/<int:ad_id>/click')
def advertisement_click(ad_id):
    """Handle advertisement click and redirect to product with discount"""
    advertisement = SellerAdvertisement.query.filter_by(id=ad_id, is_active=True, is_approved=True).first()
    
    if not advertisement:
        flash('Advertisement not found or expired.', 'error')
        return redirect(url_for('main.home'))

    if not is_advertisement_visible(advertisement)['visible']:
        flash('This promotion is not available yet or has expired.', 'error')
        return redirect(url_for('main.home'))
    
    # Store discount info in session for the product page
    session['active_discount'] = {
        'ad_id': advertisement.id,
        'discount_percentage': advertisement.discount_percentage,
        'discounted_price': float(advertisement.discounted_price),
        'expires_at': isoformat_utc_z(advertisement.expires_at)
    }

    uid = session.get('user_id')
    if uid:
        user = User.query.get(uid)
        if user and user.user_type == 'buyer':
            apply_seller_ad_to_buyer_cart_items(uid, advertisement)
            db.session.commit()

    return redirect(url_for('main.product_detail', product_id=advertisement.product_id))
