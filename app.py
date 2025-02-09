import os
from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Regexp
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from fpdf import FPDF

# Initialize app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

# Set up the database paths
app_db_path = os.path.join(os.getcwd(), 'instance', 'app.db')
dash_db_path = os.path.join(os.getcwd(), 'instance', 'dashboard.db')
os.makedirs(os.path.dirname(app_db_path), exist_ok=True)
os.makedirs(os.path.dirname(dash_db_path), exist_ok=True)

# Configure databases
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{app_db_path}"
app.config['SQLALCHEMY_BINDS'] = {
    'dashboard': f"sqlite:///{os.path.join(os.getcwd(), 'instance', 'dashboard.db')}"
}


db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# User Loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    aadhar_no = db.Column(db.String(12), unique=True, nullable=False)
    phone_no = db.Column(db.String(15), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # Farmer or Consumer
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)

class Crop(db.Model):
    __bind_key__ = 'dashboard'
    id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, nullable=False)  # Remove ForeignKey constraint
    name = db.Column(db.String(100), nullable=False)
    price_per_ton = db.Column(db.Float, nullable=False)
    quantity_available = db.Column(db.Integer, nullable=False)


class Order(db.Model):
    __bind_key__ = 'dashboard'
    id = db.Column(db.Integer, primary_key=True)
    consumer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    farmer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    crop_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    delivery_address = db.Column(db.String(255), nullable=False)
    agreement_pdf = db.Column(db.String(255), nullable=True)

# Forms
class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=100)])
    aadhar_no = StringField('Aadhar Number', validators=[
        DataRequired(), Length(min=12, max=12), Regexp(r'^\d{12}$', message='Aadhar number must be 12 digits.')
    ])
    phone_no = StringField('Phone Number', validators=[
        DataRequired(), Regexp(r'^\d{10}$', message='Phone number must be 10 digits.')
    ])
    role = SelectField('Role', choices=[('Farmer', 'Farmer'), ('Consumer', 'Consumer')], validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    captcha = StringField('Captcha: What is 3 + 4?', validators=[DataRequired()])
    submit = SubmitField('Register')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email is already registered.')

    def validate_aadhar_no(self, aadhar_no):
        user = User.query.filter_by(aadhar_no=aadhar_no.data).first()
        if user:
            raise ValidationError('Aadhar number is already registered.')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class AddCropForm(FlaskForm):
    name = StringField('Crop Name', validators=[DataRequired()])
    price_per_ton = StringField('Price Per Ton', validators=[DataRequired()])
    quantity_available = StringField('Quantity Available', validators=[DataRequired()])
    submit = SubmitField('Add Crop')


# Routes
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()

    # Debugging: Print form errors (if any)
    print("Form validation errors:", form.errors)

    if form.validate_on_submit():
        # Debugging: Print submitted form data
        print("Form Data Submitted:", form.data)

        # CAPTCHA validation
        if form.captcha.data.strip() != "7":
            flash('Incorrect CAPTCHA answer.', 'danger')
            return render_template('register.html', form=form)

        try:
            # Hash the password
            hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')

            # Check for duplicate Aadhaar or email
            existing_user_email = User.query.filter_by(email=form.email.data).first()
            existing_user_aadhar = User.query.filter_by(aadhar_no=form.aadhar_no.data).first()

            if existing_user_email:
                flash('Email is already registered. Please use a different email.', 'danger')
                return render_template('register.html', form=form)

            if existing_user_aadhar:
                flash('Aadhaar number is already registered. Please use a different Aadhaar.', 'danger')
                return render_template('register.html', form=form)

            # Create the user
            user = User(
                username=form.username.data,
                aadhar_no=form.aadhar_no.data,
                phone_no=form.phone_no.data,
                role=form.role.data,
                email=form.email.data,
                password=hashed_password
            )

            # Add user to the database
            db.session.add(user)
            db.session.commit()

            # Success message and redirect
            flash('Account created successfully! You can now log in.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            # Rollback in case of an error
            db.session.rollback()
            print(f"Error during registration: {e}")  # Debugging: Log the error
            flash('An error occurred during registration. Please try again.', 'danger')

    return render_template('register.html', form=form)



@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user)
            flash(f'Logged in successfully as {user.role}!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Login failed. Check email and password.', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/farmer_dashboard', methods=['GET', 'POST'])
@login_required
def farmer_dashboard():
    if current_user.role != 'Farmer':
        flash('Access denied.', 'danger')
        return redirect(url_for('home'))
    
    form = AddCropForm()  # Create an instance of the form
    crops = Crop.query.filter_by(farmer_id=current_user.id).all()
    
    if form.validate_on_submit():
        crop_name = form.name.data
        price_per_ton = float(form.price_per_ton.data)
        quantity = int(form.quantity_available.data)
        
        # Add new crop
        new_crop = Crop(
            farmer_id=current_user.id,
            name=crop_name,
            price_per_ton=price_per_ton,
            quantity_available=quantity
        )
        db.session.add(new_crop)
        db.session.commit()
        flash('Crop added successfully!', 'success')
        return redirect(url_for('farmer_dashboard'))
    
    return render_template('farmer_dashboard.html', crops=crops, form=form)


@app.route('/consumer_dashboard')
@login_required
def consumer_dashboard():
    if current_user.role != 'Consumer':
        flash('Access denied. You are not authorized to view this page.', 'danger')
        return redirect(url_for('home'))
    
    # Add logic to fetch data for the consumer dashboard
    # For example, display available crops, cart items, etc.
    return render_template('consumer_dashboard.html')

@app.route('/view_crops', methods=['GET'])
@login_required
def view_crops():
    if current_user.role != 'Consumer':
        return redirect(url_for('home'))
    crops = Crop.query.all()
    return render_template('view_crops.html', crops=crops)

@app.route('/cart', methods=['POST'])
@login_required
def cart():
    crop_id = request.form['crop_id']
    quantity = int(request.form['quantity'])
    crop = Crop.query.get(crop_id)
    if crop and crop.quantity_available >= quantity:
        total_price = crop.price_per_ton * quantity
        flash(f'{quantity} tons of {crop.name} added to your cart for ₹{total_price}.', 'success')
    else:
        flash('Insufficient quantity available.', 'danger')
    return redirect(url_for('view_crops'))

@app.route('/pending_requests', methods=['GET'])
@login_required
def pending_requests():
    if current_user.role != 'Farmer':
        return redirect(url_for('home'))
    orders = Order.query.filter_by(farmer_id=current_user.id).all()
    return render_template('pending_requests.html', orders=orders)

def generate_agreement(order):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Farm-to-Table Agreement", ln=True, align='C')
    pdf.cell(200, 10, txt=f"Consumer: {order.consumer_id}", ln=True)
    pdf.cell(200, 10, txt=f"Crop: {order.crop_name}", ln=True)
    pdf.cell(200, 10, txt=f"Quantity: {order.quantity} tons", ln=True)
    pdf.cell(200, 10, txt=f"Delivery Address: {order.delivery_address}", ln=True)
    pdf_file = f"agreements/order_{order.id}.pdf"
    pdf.output(pdf_file)
    return pdf_file

if __name__ == '__main__':
    app.run(debug=True)
