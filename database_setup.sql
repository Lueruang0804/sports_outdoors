-- Sports and Outdoors Ecommerce System Database
-- Run this script in your XAMPP MySQL to create the database and tables

CREATE DATABASE IF NOT EXISTS ecommerce_system;
USE ecommerce_system;

-- Users table
CREATE TABLE IF NOT EXISTS user (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    contact_number VARCHAR(20) NOT NULL,
    address_region VARCHAR(100) NOT NULL,
    address_province VARCHAR(100) NOT NULL,
    address_city VARCHAR(100) NOT NULL,
    address_barangay VARCHAR(100) NOT NULL,
    user_type ENUM('buyer', 'seller', 'admin', 'rider') NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    is_approved BOOLEAN DEFAULT FALSE,
    profile_picture VARCHAR(255),
    business_permit VARCHAR(255),
    product_categories TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Products table
CREATE TABLE IF NOT EXISTS product (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    category VARCHAR(100) NOT NULL,
    stock_quantity INT DEFAULT 0,
    image_url VARCHAR(255),
    status ENUM('active', 'inactive', 'archived') DEFAULT 'active',
    seller_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (seller_id) REFERENCES user(id) ON DELETE CASCADE
);

-- Cart table
CREATE TABLE IF NOT EXISTS cart (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
);

-- Cart Items table
CREATE TABLE IF NOT EXISTS cart_item (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cart_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cart_id) REFERENCES cart(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES product(id) ON DELETE CASCADE
);

-- Orders table
CREATE TABLE IF NOT EXISTS `order` (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_number VARCHAR(50) UNIQUE NOT NULL,
    buyer_id INT NOT NULL,
    total_amount DECIMAL(10,2) NOT NULL,
    status ENUM('pending', 'confirmed', 'preparing', 'shipped', 'delivered', 'cancelled', 'refunded') DEFAULT 'pending',
    payment_method VARCHAR(50) DEFAULT 'cash_on_delivery',
    shipping_address TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (buyer_id) REFERENCES user(id) ON DELETE CASCADE
);

-- Order Items table
CREATE TABLE IF NOT EXISTS order_item (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES `order`(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES product(id) ON DELETE CASCADE
);

-- Deliveries table
CREATE TABLE IF NOT EXISTS delivery (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    rider_id INT,
    status ENUM('pending', 'assigned', 'picked_up', 'in_transit', 'delivered') DEFAULT 'pending',
    pickup_address TEXT NOT NULL,
    delivery_address TEXT NOT NULL,
    commission_amount DECIMAL(10,2) DEFAULT 0.00,
    pod_image_url VARCHAR(500) NULL,
    pod_remarks TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES `order`(id) ON DELETE CASCADE,
    FOREIGN KEY (rider_id) REFERENCES user(id) ON DELETE SET NULL
);

-- Reviews table
CREATE TABLE IF NOT EXISTS review (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    product_id INT NOT NULL,
    rating INT NOT NULL,
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES product(id) ON DELETE CASCADE
);

-- Notifications table
CREATE TABLE IF NOT EXISTS notification (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    notification_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
);

-- Advertisements table
CREATE TABLE IF NOT EXISTS advertisement (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    image_url VARCHAR(255),
    discount_percentage INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

-- Commissions table
CREATE TABLE IF NOT EXISTS commission (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    seller_id INT NOT NULL,
    rider_id INT,
    platform_commission DECIMAL(10,2) NOT NULL,
    rider_commission DECIMAL(10,2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES `order`(id) ON DELETE CASCADE,
    FOREIGN KEY (seller_id) REFERENCES user(id) ON DELETE CASCADE,
    FOREIGN KEY (rider_id) REFERENCES user(id) ON DELETE SET NULL
);

-- Insert sample data
INSERT INTO user (email, password_hash, first_name, last_name, contact_number, address_region, address_province, address_city, address_barangay, user_type, is_verified, is_approved) VALUES
('admin@sportsoutdoors.com', 'pbkdf2:sha256:260000$hash$hash', 'Admin', 'User', '09123456789', 'NCR', 'Metro Manila', 'Quezon City', 'Diliman', 'admin', TRUE, TRUE),
('seller1@sportsoutdoors.com', 'pbkdf2:sha256:260000$hash$hash', 'John', 'Seller', '09123456788', 'NCR', 'Metro Manila', 'Makati City', 'Ayala', 'seller', TRUE, TRUE),
('buyer1@sportsoutdoors.com', 'pbkdf2:sha256:260000$hash$hash', 'Jane', 'Buyer', '09123456787', 'NCR', 'Metro Manila', 'Taguig City', 'Bonifacio', 'buyer', TRUE, TRUE),
('rider1@sportsoutdoors.com', 'pbkdf2:sha256:260000$hash$hash', 'Mike', 'Rider', '09123456786', 'NCR', 'Metro Manila', 'Pasig City', 'Ortigas', 'rider', TRUE, TRUE);

INSERT INTO product (name, description, price, category, stock_quantity, image_url, seller_id) VALUES
('Mountain Trailblazer Bike', 'High-quality mountain bike perfect for outdoor adventures. Features durable frame and excellent suspension.', 45999.00, 'Cycling & Bikes', 10, '/static/images/bike1.jpg', 2),
('Professional Camping Tent', '4-person tent with weather-resistant material. Perfect for family camping trips.', 8500.00, 'Camping & Hiking Gear', 15, '/static/images/tent1.jpg', 2),
('Premium Hiking Backpack', '50L capacity backpack with multiple compartments. Ideal for long hiking trips.', 3200.00, 'Camping & Hiking Gear', 20, '/static/images/backpack1.jpg', 2),
('Adjustable Dumbbells Set', 'Pair of adjustable dumbbells with weight plates. Perfect for home workouts.', 5500.00, 'Fitness Equipment', 25, '/static/images/dumbbells.jpg', 2),
('Sports Jersey Set', 'Breathable sports jersey and shorts set. Available in multiple colors.', 1200.00, 'Sports Apparel', 50, '/static/images/jersey.jpg', 2),
('Kayak Paddle', 'Professional kayak paddle with ergonomic grip. Suitable for all skill levels.', 2800.00, 'Water Sports', 12, '/static/images/paddle.jpg', 2);

INSERT INTO advertisement (title, description, image_url, discount_percentage, is_active) VALUES
('Limited Time Offer: 20% off all Tents!', 'Get amazing discounts on camping tents and gear', '/static/images/tent_sale.jpg', 20, TRUE),
('Unlock Your Adventure! Get 15% off All Orders!', 'Special promotion for outdoor enthusiasts', '/static/images/adventure_sale.jpg', 15, TRUE);

-- Create indexes for better performance
CREATE INDEX idx_user_email ON user(email);
CREATE INDEX idx_user_type ON user(user_type);
CREATE INDEX idx_product_category ON product(category);
CREATE INDEX idx_product_status ON product(status);
CREATE INDEX idx_order_status ON `order`(status);
CREATE INDEX idx_delivery_status ON delivery(status);
CREATE INDEX idx_notification_user ON notification(user_id);
CREATE INDEX idx_notification_read ON notification(is_read);
