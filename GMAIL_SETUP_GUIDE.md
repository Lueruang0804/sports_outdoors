# Gmail Email Setup Guide - Fix Email Sending Issues

## 🚨 Common Issues & Solutions

### **Issue 1: "Authentication failed" or "Invalid credentials"**

**Solution: Use Gmail App Passwords (Recommended)**

1. **Enable 2-Factor Authentication** on your Gmail account:
   - Go to [Google Account Security](https://myaccount.google.com/security)
   - Click "2-Step Verification"
   - Follow the setup process

2. **Generate an App Password**:
   - Go to [Google Account Security](https://myaccount.google.com/security)
   - Click "2-Step Verification"
   - Scroll down to "App passwords"
   - Click "App passwords"
   - Select "Mail" and "Other (custom name)"
   - Enter "Sports Ecommerce App"
   - Copy the 16-character password (like: `abcd efgh ijkl mnop`)

3. **Update your app.py**:
```python
app.config['MAIL_USERNAME'] = 'your-actual-email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your-16-character-app-password'  # No spaces
```

### **Issue 2: "Connection refused" or "SMTP server not responding"**

**Solution: Check your network and Gmail settings**

1. **Verify Gmail SMTP settings**:
```python
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
```

2. **Try alternative port** (if 587 doesn't work):
```python
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True  # Use SSL instead of TLS
app.config['MAIL_USE_TLS'] = False
```

### **Issue 3: "Less secure app access" error**

**Solution: Enable App Passwords (Recommended) or Less Secure Apps**

**Option A: Use App Passwords (Recommended)**
- Follow the App Password setup above

**Option B: Enable Less Secure Apps (Not Recommended)**
- Go to [Google Account Security](https://myaccount.google.com/security)
- Click "Less secure app access"
- Turn it ON
- ⚠️ **Warning**: This is less secure

## 🔧 Step-by-Step Setup

### **Step 1: Update your app.py file**

Replace the placeholder values in your `app.py`:

```python
# Replace these lines in app.py
app.config['MAIL_USERNAME'] = 'your-actual-email@gmail.com'  # Your real Gmail
app.config['MAIL_PASSWORD'] = 'your-16-character-app-password'  # App password
```

### **Step 2: Test your configuration**

1. **Edit the test script**:
   - Open `test_email.py`
   - Update the MAIL_USERNAME and MAIL_PASSWORD
   - Save the file

2. **Run the test**:
```bash
python test_email.py
```

3. **Check your email**:
   - Look in your inbox
   - Check spam/junk folder
   - If you receive the test email, your setup is working!

### **Step 3: Test the verification system**

1. **Start your application**:
```bash
python run.py
```

2. **Register a new account**:
   - Go to http://localhost:5000/register
   - Fill out the registration form
   - Submit the form

3. **Check for verification email**:
   - Look in your inbox
   - Check spam/junk folder
   - Click the verification link

## 🛠️ Alternative Email Providers

If Gmail continues to have issues, try these alternatives:

### **Outlook/Hotmail**:
```python
app.config['MAIL_SERVER'] = 'smtp-mail.outlook.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@outlook.com'
app.config['MAIL_PASSWORD'] = 'your-password'
```

### **Yahoo Mail**:
```python
app.config['MAIL_SERVER'] = 'smtp.mail.yahoo.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@yahoo.com'
app.config['MAIL_PASSWORD'] = 'your-app-password'
```

## 🔍 Debugging Tips

### **Enable Debug Mode**:
Add this to your `app.py` to see detailed error messages:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### **Check Console Output**:
Look for error messages in your terminal when you try to register.

### **Common Error Messages**:

1. **"Authentication failed"**:
   - Wrong password or username
   - Need to use App Password

2. **"Connection refused"**:
   - Wrong SMTP server or port
   - Network/firewall issues

3. **"SMTPAuthenticationError"**:
   - Gmail security settings blocking the connection
   - Need to enable 2FA and App Password

## ✅ Quick Test Checklist

- [ ] Gmail account has 2-Factor Authentication enabled
- [ ] App Password generated and copied correctly
- [ ] app.py updated with real credentials
- [ ] Test email script runs successfully
- [ ] Verification email received in inbox
- [ ] Verification link works when clicked

## 🆘 Still Having Issues?

If you're still having problems:

1. **Try a different Gmail account**
2. **Use a different email provider** (Outlook, Yahoo)
3. **Check your firewall/antivirus settings**
4. **Try using a VPN** (some networks block SMTP)
5. **Contact your ISP** (some block SMTP ports)

## 📞 Need Help?

If you continue to have issues, please share:
1. The exact error message you see
2. Your Gmail account type (personal, business, etc.)
3. Whether you've enabled 2FA
4. Whether you've generated an App Password
