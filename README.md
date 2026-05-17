# 🏃‍♂️ Sports and Outdoors Ecommerce System

A comprehensive, full-featured ecommerce platform built with Flask and MySQL for sports and outdoor equipment. This system provides a complete solution for managing an online sports and outdoor equipment store with multiple user roles and advanced features.

## ✨ Features

### 🔐 User Management
- **Multi-role System**: Buyer, Seller, Admin, and Rider accounts
- **Email Verification**: Gmail integration for account verification
- **Admin Approval**: All accounts require admin approval
- **Profile Management**: Complete user profiles with address information
- **Secure Authentication**: Password hashing and session management

### 🛍️ Product Management
- **CRUD Operations**: Create, Read, Update, Delete products
- **Image Uploads**: Product images with secure file handling
- **Category Management**: Organized product categories
- **Stock Management**: Inventory tracking
- **Product Status**: Active, Inactive, and Archived states
- **Search & Filter**: Advanced product search and filtering

### 🛒 Shopping Experience
- **Shopping Cart**: Add items without inventory deduction
- **Order Management**: Complete order lifecycle
- **Payment Methods**: Cash on Delivery (COD) support
- **Order Tracking**: Real-time order status updates
- **Product Reviews**: Star ratings and comments
- **Wishlist**: Save favorite products

### 📊 Business Features
- **Sales Analytics**: Comprehensive sales reports with charts
- **Commission System**: Platform and rider commission tracking
- **Advertisement Management**: Promotional campaigns
- **Notification System**: Real-time updates for all users
- **Delivery Tracking**: Complete delivery management

### 🎨 User Interface
- **Responsive Design**: Mobile-friendly interface
- **Modern UI/UX**: Clean and attractive design
- **Bootstrap Integration**: Professional styling
- **Interactive Elements**: Dynamic forms and components
- **Accessibility**: User-friendly navigation

## 🚀 Quick Start

### Option 1: Automated Setup (Recommended)

1. **Run the setup script**
   ```bash
   python setup_system.py
   ```

2. **Start the application**
   - Windows: Double-click `start.bat`
   - Linux/Mac: Run `./start.sh`

3. **Access the system**
   - Open your browser and go to `http://localhost:5000`

### Option 2: Manual Setup

#### Prerequisites
- Python 3.8 or higher
- XAMPP (for MySQL database)
- Git

#### Installation Steps

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd ecommerce_system
   ```

2. **Set up virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up database**
   - Start XAMPP and ensure MySQL is running
   - Import the `database_setup.sql` file into MySQL
   - Update database credentials in `app.py` if needed

5. **Create sample data (optional)**
   ```bash
   python seed_data.py
   ```

6. **Run the application**
   ```bash
   python run.py
   ```

7. **Access the application**
   - Open your browser and go to `http://localhost:5000`

### Option 3: Supabase Setup (PostgreSQL)

1. **Create and configure environment file**
   - Copy `.env.example` to `.env`
   - Set:
   ```env
   DATABASE_URL=postgresql+psycopg2://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres?sslmode=require
   SECRET_KEY=your-secret-key
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python run.py
   ```

4. **Run Supabase preflight checks**
   ```bash
   python supabase_preflight.py
   ```

5. **Verify core application flow**
   ```bash
   python test_system.py
   ```

6. **Access the application**
   - Open your browser and go to `http://localhost:5000`

## 👥 User Roles & Features

### 🔧 Admin
- **Dashboard**: Platform overview and analytics
- **User Management**: Approve/disapprove accounts, delete users
- **Product Oversight**: View all products across the platform
- **Order Management**: Monitor all orders
- **Advertisement Management**: Create and manage promotional campaigns
- **Commission Tracking**: View platform commission analytics
- **Chat Support**: Customer support management
- **Notifications**: System-wide notifications

### 🏪 Seller
- **Dashboard**: Sales overview and statistics
- **Product Management**: Add, edit, delete, archive, and retrieve products
- **Order Management**: Process and update order status
- **Sales Reports**: Detailed analytics with charts and date filtering
- **Commission Tracking**: View seller commission earnings
- **Profile Management**: Update business information
- **Notifications**: Order and system notifications

### 🛒 Buyer
- **Homepage**: Featured products and categories
- **Product Browsing**: Search, filter, and view products
- **Shopping Cart**: Add items and manage cart
- **Order Management**: Place orders and track status
- **Order History**: View past and current orders
- **Product Reviews**: Rate and review products
- **Wishlist**: Save favorite products
- **Profile Management**: Update personal information
- **Notifications**: Order updates and promotions

### 🚚 Rider
- **Dashboard**: Delivery overview and statistics
- **Delivery Management**: View assigned deliveries
- **Available Deliveries**: Accept new delivery assignments
- **Status Updates**: Update delivery progress (picked up, in transit, delivered)
- **Commission Tracking**: View earnings and commission history
- **Profile Management**: Update rider information
- **Chat Support**: Communication with customers
- **Notifications**: Delivery assignments and updates

## 🗄️ Database Schema

The system uses a comprehensive database schema with the following main tables:

- **`users`** - User accounts, profiles, and authentication
- **`products`** - Product catalog with images and categories
- **`orders`** - Order information and status tracking
- **`order_items`** - Individual items within orders
- **`deliveries`** - Delivery tracking and rider assignments
- **`commissions`** - Commission tracking for platform and riders
- **`advertisements`** - Promotional campaigns and discounts
- **`notifications`** - System-wide notification management
- **`reviews`** - Product ratings and customer feedback
- **`carts`** - Shopping cart management
- **`cart_items`** - Individual cart items

## 🔧 Configuration

### Environment Variables
```python
# Flask Configuration
FLASK_ENV = 'development'  # or 'production'
SECRET_KEY = 'your-secret-key-here'

# Database Configuration
SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:@localhost/ecommerce_system'

# Email Configuration (for verification)
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USERNAME = 'your-email@gmail.com'
MAIL_PASSWORD = 'your-app-password'
```

### Database Setup
1. Start XAMPP and ensure MySQL is running
2. Create a database named `ecommerce_system`
3. Import the `database_setup.sql` file
4. Update connection credentials in `app.py` if needed

### Supabase Database Setup
1. Create a Supabase project
2. Copy the Postgres connection string into `DATABASE_URL`
3. Ensure `sslmode=require` is present in the connection string
4. Start the app and let SQLAlchemy create tables automatically
5. Run `python test_system.py` to validate core functionality

## 📱 API Endpoints

### Authentication
- `POST /auth/register` - User registration with email verification
- `POST /auth/login` - User authentication
- `GET /auth/logout` - User logout
- `GET /auth/verify/<token>` - Email verification

### Products
- `GET /products` - List all products with search and filter
- `GET /products/<id>` - Get detailed product information
- `POST /seller/products/add` - Add new product (Seller only)
- `PUT /seller/products/edit/<id>` - Edit product (Seller only)
- `DELETE /seller/products/delete/<id>` - Delete product (Seller only)
- `POST /seller/products/archive/<id>` - Archive product (Seller only)
- `POST /seller/products/retrieve/<id>` - Retrieve archived product (Seller only)

### Orders & Cart
- `POST /buyer/cart/add` - Add item to shopping cart
- `GET /buyer/cart` - View shopping cart
- `POST /buyer/orders/place` - Place order from cart
- `GET /buyer/orders` - View order history (Buyer only)
- `GET /seller/orders` - View orders (Seller only)
- `POST /buyer/orders/<id>/cancel` - Cancel order
- `POST /buyer/orders/<id>/refund` - Request refund

### User Management
- `GET /admin/users` - List all users (Admin only)
- `POST /admin/users/<id>/approve` - Approve user account (Admin only)
- `POST /admin/users/<id>/disapprove` - Disapprove user account (Admin only)
- `DELETE /admin/users/<id>` - Delete user account (Admin only)

## 🧪 Test Accounts

After running the setup script, you can use these test accounts:

- **Admin**: `admin@sportsandoutdoors.com` / `admin123`
- **Seller**: `seller1@sportsandoutdoors.com` / `seller123`
- **Buyer**: `buyer1@sportsandoutdoors.com` / `buyer123`
- **Rider**: `rider1@sportsandoutdoors.com` / `rider123`

## 📁 Project Structure

```
ecommerce_system/
├── app.py                 # Main Flask application
├── models.py              # Database models
├── config.py              # Configuration settings
├── run.py                 # Application runner
├── requirements.txt       # Python dependencies
├── database_setup.sql     # Database schema
├── seed_data.py          # Sample data generator
├── setup_system.py       # Automated setup script
├── start.bat             # Windows startup script
├── start.sh              # Linux/Mac startup script
├── routes/               # Route handlers
│   ├── __init__.py
│   ├── auth.py           # Authentication routes
│   ├── main.py           # Public routes
│   ├── buyer.py          # Buyer-specific routes
│   ├── seller.py         # Seller-specific routes
│   ├── admin.py          # Admin-specific routes
│   └── rider.py          # Rider-specific routes
├── templates/            # HTML templates
│   ├── base.html         # Base template
│   ├── auth/             # Authentication templates
│   ├── main/             # Public page templates
│   ├── buyer/            # Buyer dashboard templates
│   ├── seller/           # Seller dashboard templates
│   ├── admin/            # Admin dashboard templates
│   └── rider/            # Rider dashboard templates
└── static/               # Static files
    ├── css/              # Stylesheets
    ├── js/               # JavaScript files
    └── uploads/          # Uploaded files
        ├── products/     # Product images
        ├── profiles/     # Profile pictures
        ├── documents/    # Business permits
        └── advertisements/ # Advertisement images
```

## 🔒 Security Features

- **Password Hashing**: Secure password storage using Werkzeug
- **Session Management**: Secure user sessions
- **File Upload Security**: Secure filename handling and validation
- **Input Validation**: Server-side validation for all inputs
- **SQL Injection Protection**: SQLAlchemy ORM protection
- **XSS Protection**: Template escaping and validation

## 🚀 Deployment

### Production Deployment
1. Set `FLASK_ENV=production` in environment variables
2. Use a production WSGI server like Gunicorn
3. Set up a reverse proxy with Nginx
4. Use a production database (PostgreSQL recommended)
5. Set up SSL certificates for HTTPS
6. Configure proper logging and monitoring

### Docker Deployment
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "run.py"]
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

For support and questions:
- Create an issue in the repository
- Contact the development team
- Check the documentation

## 🎯 Roadmap

- [ ] Payment gateway integration (PayPal, Stripe)
- [ ] Real-time chat system
- [ ] Mobile app development
- [ ] Advanced analytics dashboard
- [ ] Multi-language support
- [ ] API documentation with Swagger
- [ ] Automated testing suite
- [ ] Performance optimization

---

**🏃‍♂️ Sports and Outdoors Ecommerce System - Your complete solution for online sports equipment retail!**