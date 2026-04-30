from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import pickle
import numpy as np
import pandas as pd
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_very_secret_key_here'  # Change this for production!

# Load model and encoders
with open('model.pkl', 'rb') as f:
    model = pickle.load(f)

with open('label_encoders.pkl', 'rb') as f:
    label_encoders = pickle.load(f)

# Database setup
def init_db():
    conn = sqlite3.connect('vendors.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recommended_vendors
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  supplier_name TEXT,
                  price REAL,
                  location TEXT,
                  defect_rate REAL,
                  total_costs REAL,
                  confidence_score REAL,
                  supplier_email TEXT,
                  timestamp DATETIME)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS suppliers 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  email TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  registered_on DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# Admin credentials (for demonstration only)
ADMIN_CREDENTIALS = {'username': 'admin', 'password': 'admin123'}

# Supplier Authentication Routes
@app.route('/supplier/register', methods=['GET','POST'])
def supplier_register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']  # Plain text password
        
        try:
            conn = sqlite3.connect('vendors.db')
            c = conn.cursor()
            # Store plain text password
            c.execute('INSERT INTO suppliers (email, password) VALUES (?, ?)', 
                     (email, password))  # No hashing
            conn.commit()
            return redirect(url_for('supplier_login'))
        except sqlite3.IntegrityError:
            return "Email already exists"
        finally:
            conn.close()
    return render_template('supplier_register.html')

# In supplier_login route (app.py)
@app.route('/supplier/login', methods=['GET', 'POST'])
def supplier_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = sqlite3.connect('vendors.db')
        c = conn.cursor()
        c.execute('SELECT * FROM suppliers WHERE email = ?', (email,))
        user = c.fetchone()
        conn.close()
        
        # Compare plain text passwords
        if user and user[2] == password:  # Direct comparison
            session['supplier_logged_in'] = True
            session['supplier_email'] = email
            return redirect(url_for('home'))
        return jsonify({'error': 'Invalid email or password'}), 401
    return render_template('supplier_login.html')

@app.route('/supplier/logout')
def supplier_logout():
    session.pop('supplier_logged_in', None)
    session.pop('supplier_email', None)
    return redirect(url_for('supplier_login'))

# Main Application Routes
@app.route('/')
def home():
    if not session.get('supplier_logged_in'):
        return redirect(url_for('supplier_login'))
    return render_template('index.html')

@app.route('/predict', methods=['POST'])
def predict():
    try:
        if not session.get('supplier_logged_in'):
            return jsonify({'error': 'Not authenticated'}), 401
        
        data = request.form.to_dict()
        original_data = data.copy()
        
        # Convert numerical fields
        numerical_features = [
            'Price', 'Availability', 'Number of products sold',
            'Revenue generated', 'Stock levels', 'Lead times',
            'Order quantities', 'Shipping times', 'Shipping costs',
            'Lead time', 'Production volumes', 'Manufacturing lead time',
            'Manufacturing costs', 'Defect rates', 'Costs'
        ]
        
        for feature in numerical_features:
            data[feature] = float(data[feature])
        
        # Encode categorical features
        categorical_mapping = {
            'Shipping carriers': ['Carrier A', 'Carrier B', 'Carrier C'],
            'Supplier name': ['Supplier 1', 'Supplier 2', 'Supplier 3', 'Supplier 4', 'Supplier 5'],
            'Location': ['Mumbai', 'Kolkata', 'Delhi', 'Bangalore', 'Chennai'],
            'Transportation modes': ['Road', 'Air', 'Rail', 'Sea']
        }
        
        for feature, categories in categorical_mapping.items():
            le = label_encoders[feature]
            if data[feature] not in categories:
                raise ValueError(f"Invalid value for {feature}")
            data[feature] = le.transform([data[feature]])[0]
        
        # Create feature array
        features = [
            data['Price'],
            data['Availability'],
            data['Number of products sold'],
            data['Revenue generated'],
            data['Stock levels'],
            data['Lead times'],
            data['Order quantities'],
            data['Shipping times'],
            data['Shipping carriers'],
            data['Shipping costs'],
            data['Supplier name'],
            data['Location'],
            data['Lead time'],
            data['Production volumes'],
            data['Manufacturing lead time'],
            data['Manufacturing costs'],
            data['Defect rates'],
            data['Transportation modes'],
            data['Costs']
        ]
        
        # Make prediction
        proba = model.predict_proba([features])[0][1]
        prediction = model.predict([features])[0]
        
        # Store in database if recommended
        if prediction == 1:
            supplier_email = session['supplier_email']
            conn = sqlite3.connect('vendors.db')
            c = conn.cursor()
            c.execute('''INSERT INTO recommended_vendors 
                      (supplier_name, price, location, defect_rate, total_costs,
                       confidence_score, supplier_email, timestamp)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                     (original_data['Supplier name'],
                      original_data['Price'],
                      original_data['Location'],
                      original_data['Defect rates'],
                      original_data['Costs'],
                      float(round(proba * 100, 1)),
                      supplier_email,
                      datetime.now()))
            conn.commit()
            conn.close()
        
        return jsonify({
            'prediction': int(prediction),
            'probability': float(round(proba * 100, 1)),
            'status': 'success'
        })
        
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'})

# Admin Routes
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if (request.form['username'] == ADMIN_CREDENTIALS['username'] and 
            request.form['password'] == ADMIN_CREDENTIALS['password']):
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        return "Invalid credentials"
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('vendors.db')
    c = conn.cursor()
    c.execute('SELECT * FROM recommended_vendors')
    vendors = c.fetchall()
    conn.close()
    
    return render_template('admin_dashboard.html', vendors=vendors)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/delete/<int:vendor_id>', methods=['DELETE'])
def delete_vendor(vendor_id):
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        conn = sqlite3.connect('vendors.db')
        c = conn.cursor()
        c.execute('DELETE FROM recommended_vendors WHERE id = ?', (vendor_id,))
        conn.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(debug=True)