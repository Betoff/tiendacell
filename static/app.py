from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
import os
from werkzeug.utils import secure_filename
import urllib.parse

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        SQLALCHEMY_DATABASE_URI='sqlite:///' + os.path.join(app.instance_path, 'tiendacell.db'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=os.path.join('static', 'img', 'products')
    )
    
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    
    try:
        os.makedirs(os.path.join(app.static_folder, 'img', 'products'))
    except OSError:
        pass
    
    # Importamos la base de datos aquí para evitar errores de importación circular
    from models import db
    from models.product import Product, Category
    from models.user import User
    
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
        # Inicializar categorías si no existen
        if not Category.query.first():
            categories = [
                Category(name='Apple'),
                Category(name='Android')
            ]
            db.session.add_all(categories)
            db.session.commit()
            
        # Crear productos de ejemplo si no existen
        if not Product.query.first():
            # Ejemplos de Apple
            products = [
                Product(name='iPhone 13 Pro Max', price=899.99, stock=10, category_id=1),
                Product(name='iPhone 14', price=799.99, stock=15, category_id=1),
                Product(name='iPhone 16', price=1099.99, stock=5, category_id=1),
                # Ejemplos de Android
                Product(name='Motorola G24', price=249.99, stock=20, category_id=2),
                Product(name='Xiaomi 34', price=399.99, stock=8, category_id=2),
                Product(name='Samsung Galaxy A16', price=329.99, stock=12, category_id=2),
            ]
            db.session.add_all(products)
            db.session.commit()
            
        # Crear usuario admin si no existe
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', is_admin=True)
            admin.set_password('adminpass')  # Cambiar a una contraseña más segura
            db.session.add(admin)
            db.session.commit()
    
    # Rutas para el cliente
    @app.route('/')
    def index():
        products = Product.query.all()
        categories = Category.query.all()
        return render_template('index.html', products=products, categories=categories)
    
    @app.route('/category/<int:category_id>')
    def category(category_id):
        category = Category.query.get_or_404(category_id)
        products = Product.query.filter_by(category_id=category_id).all()
        categories = Category.query.all()
        return render_template('category.html', category=category, products=products, categories=categories)
    
    @app.route('/cart')
    def cart():
        categories = Category.query.all()
        return render_template('cart.html', categories=categories)
    
    @app.route('/api/add-to-cart', methods=['POST'])
    def add_to_cart():
        product_id = request.json.get('product_id')
        product = Product.query.get_or_404(product_id)
        
        if 'cart' not in session:
            session['cart'] = []
            
        # Check if product already in cart
        for item in session['cart']:
            if item['id'] == product_id:
                item['quantity'] += 1
                session.modified = True
                return jsonify({'success': True})
                
        session['cart'].append({
            'id': product_id,
            'name': product.name,
            'price': product.price,
            'quantity': 1
        })
        session.modified = True
        return jsonify({'success': True})
    
    @app.route('/api/cart')
    def get_cart():
        if 'cart' not in session:
            return jsonify([])
        return jsonify(session['cart'])
    
    @app.route('/checkout')
    def checkout():
        if 'cart' not in session or not session['cart']:
            flash('Tu carrito está vacío')
            return redirect(url_for('index'))
            
        # Preparar mensaje para WhatsApp
        message = "Hola! Me gustaría realizar la siguiente compra:\n\n"
        total = 0
        
        for item in session['cart']:
            product = Product.query.get(item['id'])
            subtotal = item['price'] * item['quantity']
            total += subtotal
            message += f"- {item['name']} x{item['quantity']}: ${subtotal:.2f}\n"
            
        message += f"\nTotal: ${total:.2f}"
        
        # Formatear mensaje para URL de WhatsApp
        whatsapp_number = "+543764225116"  # Tu número de WhatsApp
        encoded_message = urllib.parse.quote(message)
        whatsapp_url = f"https://wa.me/{whatsapp_number}?text={encoded_message}"
        
        # Limpiar carrito después de checkout
        session.pop('cart', None)
        
        return redirect(whatsapp_url)
    
    # Rutas para el panel de administración
    @app.route('/admin/login', methods=['GET', 'POST'])
    def admin_login():
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            
            user = User.query.filter_by(username=username).first()
            
            if user and user.check_password(password) and user.is_admin:
                session['admin_id'] = user.id
                return redirect(url_for('admin_dashboard'))
            
            flash('Credenciales inválidas')
            
        return render_template('admin/login.html')
    
    @app.route('/admin/logout')
    def admin_logout():
        session.pop('admin_id', None)
        return redirect(url_for('index'))
    
    @app.route('/admin')
    def admin_dashboard():
        if 'admin_id' not in session:
            return redirect(url_for('admin_login'))
            
        products_count = Product.query.count()
        categories = Category.query.all()
        low_stock = Product.query.filter(Product.stock < 5).all()
        
        return render_template('admin/dashboard.html', 
                              products_count=products_count,
                              categories=categories,
                              low_stock=low_stock)
    
    @app.route('/admin/inventory')
    def admin_inventory():
        if 'admin_id' not in session:
            return redirect(url_for('admin_login'))
            
        products = Product.query.all()
        return render_template('admin/inventory.html', products=products)
    
    @app.route('/admin/product/new', methods=['GET', 'POST'])
    def add_product():
        if 'admin_id' not in session:
            return redirect(url_for('admin_login'))
            
        categories = Category.query.all()
        
        if request.method == 'POST':
            name = request.form['name']
            price = float(request.form['price'])
            description = request.form['description']
            stock = int(request.form['stock'])
            category_id = int(request.form['category_id'])
            
            # Manejar la carga de la imagen
            image_path = None
            if 'image' in request.files:
                file = request.files['image']
                if file.filename:
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], filename))
                    image_path = os.path.join('img', 'products', filename)
            
            product = Product(
                name=name,
                price=price,
                description=description,
                stock=stock,
                category_id=category_id,
                image_path=image_path
            )
            
            db.session.add(product)
            db.session.commit()
            
            flash('Producto agregado exitosamente')
            return redirect(url_for('admin_inventory'))
            
        return render_template('admin/add_product.html', categories=categories)
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
