from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy

from datetime import datetime, timedelta
from random   import randint
from passlib  import pwd, hash

app = Flask(__name__)
app.secret_key = 'tGtkxe9Zujgsz3DMx2Xa3c69ykkwAC2GhmH2'

app.config['SQLALCHEMY_DATABASE_URI'] = app.open_resource('db.txt').read().decode('ascii')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

app.debug = True



class Sprint(db.Model):
    id    = db.Column(db.Integer, primary_key=True)
    name  = db.Column(db.String(150))
    description = db.Column(db.String(1000))
    start = db.Column(db.DateTime)
    end   = db.Column(db.DateTime)
    items = db.relationship('Item', backref='sprint', lazy=True)



class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status      = db.Column(db.String(50))
    sprint_id   = db.Column(db.Integer, db.ForeignKey('sprint.id'))
    name        = db.Column(db.String(250))
    description = db.Column(db.String(1000))
    created     = db.Column(db.DateTime)
    created_by_id  = db.Column(db.Integer, db.ForeignKey('user.id'))
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'))



class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'))
    txt     = db.Column(db.String(1000))
    created = db.Column(db.DateTime)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))



class User(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(50), nullable=False)
    username = db.Column(db.String(50), nullable=False)
    password = db.Column(db.String(100))
    temp_pw  = db.Column(db.String(20))
    comments       = db.relationship('Comment', backref='created_by',  lazy=True, foreign_keys='Comment.created_by_id')
    assigned_items = db.relationship('Item',    backref='assigned_to', lazy=True, foreign_keys='Item.assigned_to_id')
    created_items = db.relationship('Item',    backref='created_by',  lazy=True, foreign_keys='Item.created_by_id')
    selected_sprint_id = db.Column(db.Integer, db.ForeignKey('sprint.id'))
    sheriff = db.Column(db.Boolean, default=False)
    admin   = db.Column(db.Boolean, default=False)










@app.route('/')
def home():
    url = '/sprints'

    if 'sprint' in session:
        id  = session['sprint']['id']
        url = url + '/' + str(id)

    return redirect(url)





@app.before_request
def check_user():
    endpt = request.endpoint

    if 'user' in session:
        if 'change_pw' in session and endpt not in ['change_password', 'logout', 'static']:
            return redirect('users/' + str(session['user']['id']) + '/change')

    elif endpt != 'login' and endpt != 'static':
        return redirect('/login')





@app.context_processor
def inject_date():
    return {'today': datetime.now() }





@app.route('/backlog')
def backlog():
    items = Item.query.filter_by(sprint_id=None).order_by(Item.created.desc()).all()
    return render_template('backlog.html', title='Backlog', items=items)





@app.route('/backlog/new', methods=['GET', 'POST'])
def new_item():
    if 'submit' in request.form:
        name = request.form['name']
        desc = request.form['desc'] if request.form['desc'] else None
        created_by_id  = session['user']['id']
        assigned_to_id = int(request.form['user'])   if 'user'   in request.form and request.form['user']   else None
        sprint_id      = int(request.form['sprint']) if 'sprint' in request.form and request.form['sprint'] else None

        if not session['user']['sheriff'] and not session['user']['admin']:
            assigned_to_id = None
            sprint_id = None

        if name:
            item = Item(name=name, status='Pending', sprint_id=sprint_id, created=datetime.utcnow(), created_by_id=created_by_id, assigned_to_id=assigned_to_id, description=desc)
            db.session.add(item)

            db.session.commit()
            return redirect('/backlog')

    return render_template('edit-item.html', title='New Item', sprints=Sprint.query.all(), users=User.query.all())





@app.route('/sprints')
def sprints():
    sprints = Sprint.query.order_by(Sprint.start.desc()).all()
    return render_template('sprints.html', title='Sprints', sprints=sprints)





STATUS_COLORS = {'Pending': 'secondary', 'In Process': 'primary', 'Testing': 'warning', 'Complete': 'success'}
STATUS_LIST   = ['Pending', 'In Process', 'Testing', 'Complete']

@app.route('/sprints/<int:id>')
def sprint(id):
    sprint = Sprint.query.get(id)
    items  = Item.query.filter_by(sprint_id=id).all()
    days_left = (sprint.end - datetime.utcnow()).days
    
    data = []
    for status in STATUS_LIST:
        filtered = [item for item in items if item.status == status]

        data.append({
            'status': status,
            'color':  STATUS_COLORS[status],
            'count':  len(filtered),
            'items':  filtered
        })

    return render_template('sprint.html', title=sprint.name, data=data, sprint=sprint, days_left=days_left)





@app.route('/sprints/<int:id>/select')
def select_sprint(id):
    sprint = Sprint.query.get(id)
    user   = User.query.get(session['user']['id'])

    session['sprint'] = { 'id': id, 'name': sprint.name }
    user.selected_sprint_id = id

    db.session.commit()
    return redirect('/sprints')





@app.route('/sprints/new', methods=['GET', 'POST'])
def new_sprint():
    if not session['user']['sheriff'] and not session['user']['admin']:
        return redirect('/sprints')

    latest = Sprint.query.order_by(Sprint.end.desc()).first()

    if 'submit' in request.form:
        name  = request.form['name'] if request.form['name'] else None
        start = datetime.strptime(request.form['start'], '%Y-%m-%d') if request.form['start'] else None
        end   = datetime.strptime(request.form['end'],   '%Y-%m-%d') if request.form['end']   else None
        desc  = request.form['desc'] if request.form['desc'] else None

        if name and start and end:
            if end > start and not overlap(start, end):
                sprint = Sprint(name=name, start=start, end=end, description=desc)

                db.session.add(sprint)
                db.session.commit()
                return redirect('/sprints')

    default_start = (latest.end + timedelta(days=1)) if latest else datetime.utcnow()
    default_end   = default_start + timedelta(days=14)

    default_start = default_start.strftime('%Y-%m-%d')
    default_end   = default_end.strftime('%Y-%m-%d')

    return render_template('edit-sprint.html', title='New Sprint', default_start=default_start, default_end=default_end)





def overlap(start, end):
    before = Sprint.query.filter(Sprint.end < start).count()
    after  = Sprint.query.filter(Sprint.start > end).count()
    total  = Sprint.query.count()

    return total - before - after





@app.route('/sprints/<int:id>/edit', methods=['GET', 'POST'])
def edit_sprint(id):
    if not session['user']['sheriff'] and not session['user']['admin']:
        return redirect('/sprints')

    sprint = Sprint.query.get(id)

    if 'submit' in request.form:
        name  = request.form['name'] if request.form['name'] else None
        start = datetime.strptime(request.form['start'], '%Y-%m-%d') if request.form['start'] else None
        end   = datetime.strptime(request.form['end'],   '%Y-%m-%d') if request.form['end']   else None
        desc  = request.form['desc'] if request.form['desc'] else None

        if name and start and end:
            if end > start and overlap(start, end) == 1:
                sprint.name  = name
                sprint.start = start
                sprint.end   = end
                sprint.description = desc

                db.session.commit()
                return redirect('/sprints')

    return render_template('edit-sprint.html', title='Edit Sprint', sprint=sprint)





@app.route('/sprints/<int:id>/delete', methods=['GET', 'POST'])
def delete_sprint(id):
    if not session['user']['sheriff'] and not session['user']['admin']:
        return redirect('/sprints')

    sprint = Sprint.query.get(id)
    
    if 'submit' in request.form:
        db.session.delete(sprint)
        db.session.commit()
        return redirect('/sprints')

    return render_template('delete.html', title=sprint.name, type='Sprint', cancel='/sprints')





@app.route('/items/<int:id>', methods=['GET', 'POST'])
def item(id):
    item = Item.query.get(id)

    if 'submit' in request.form:
        text = request.form['comment'] if request.form['comment'] else None
        
        if text:
            comment = Comment(txt=text, item_id=id, created=datetime.utcnow(), created_by_id=session['user']['id'])
            db.session.add(comment)
            db.session.commit()

    comments = Comment.query.filter_by(item_id=id).order_by(Comment.created)

    return render_template('item.html', item=item, comments=comments, status_colors=STATUS_COLORS)





@app.route('/items/<int:id>/activate')
def activate_item(id):
    if session['user']['sheriff'] or session['user']['admin']:
        if 'sprint' in session:
            item = Item.query.get(id)
            item.sprint_id = session['sprint']['id']
            db.session.commit()

    return redirect('/backlog')





@app.route('/items/<int:id>/edit', methods=['GET', 'POST'])
def edit_item(id):
    item = Item.query.get(id)

    if item.sprint_id or item.created_by.id != session['user']['id']:
        if not session['user']['sheriff'] and not session['user']['admin']:
            return redirect('/backlog')

    if 'submit' in request.form:
        name    = request.form['name']
        assigned_to_id = int(request.form['user'])   if 'user'   in request.form and request.form['user']   else None
        sprint_id      = int(request.form['sprint']) if 'sprint' in request.form and request.form['sprint'] else None
        desc = request.form['desc'] if request.form['desc'] else None
        
        if name:
            item.name = name
            item.assigned_to_id = assigned_to_id
            redirect_url   = '/sprints/' + str(item.sprint_id) if item.sprint_id else '/backlog'
            item.sprint_id = sprint_id
            item.description = desc

            db.session.commit()
            return redirect(redirect_url)

    return render_template('edit-item.html', title='Edit Item', item=item, sprint=item.sprint, sprints=Sprint.query.all(), users=User.query.all())





@app.route('/items/<int:id>/delete', methods=['GET', 'POST'])
def delete_item(id):
    item = Item.query.get(id)

    if item.sprint_id or item.created_by.id != session['user']['id']:
        if not session['user']['sheriff'] and not session['user']['admin']:
            return redirect('/backlog')

    if 'submit' in request.form:
        db.session.delete(item)
        db.session.commit()
        return redirect('/backlog')

    return render_template('delete.html', title=item.name, type='Item', cancel='/backlog')





@app.route('/items/<int:id>/demote')
def demote_item(id):
    item      = Item.query.get(id)
    sprint_id = item.sprint_id
    index     = STATUS_LIST.index(item.status) if item.status in STATUS_LIST else None

    if index == None:
        item.status = STATUS_LIST[0]
        item.sprint_id = None
    else:
        item.status = STATUS_LIST[index - 1] if index > 0 else STATUS_LIST[0]

    db.session.commit()
    return redirect('/sprints/' + str(sprint_id))





@app.route('/items/<int:id>/promote')
def promote_item(id):
    item      = Item.query.get(id)
    sprint_id = item.sprint_id
    index     = STATUS_LIST.index(item.status) if item.status in STATUS_LIST else None

    if index == None:
        item.status = STATUS_LIST[0]
        item.sprint_id = None
    else:
        item.status = STATUS_LIST[index + 1] if index < len(STATUS_LIST) - 1 else STATUS_LIST[len(STATUS_LIST) - 1]

    db.session.commit()
    return redirect('/sprints/' + str(sprint_id))





@app.route('/items/<int:id>/backlog')
def backlog_item(id):
    item = Item.query.get(id)
    sprint_id = item.sprint_id

    if session['user']['sheriff'] or session['user']['admin']:
        item.status = STATUS_LIST[0]
        item.sprint_id = None
        db.session.commit()

    return redirect('/sprints/' + str(sprint_id))





@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'submit' in request.form: 
        username = request.form['username'] if request.form['username'] else None
        password = request.form['password'] if request.form['password'] else None

        if username: #and password:
            user = User.query.filter_by(username=username).first()
            auth = False

            if user:
                if user.temp_pw:
                    if password == user.temp_pw: auth = True

                elif user.password:
                    if hash.pbkdf2_sha256.verify(password, user.password): auth = True
            
            if auth:
                session['user'] = { 'id': user.id, 'name': user.name, 'username': user.username, 'sheriff': user.sheriff, 'admin': user.admin }
                if user.temp_pw: session['change_pw'] = True 

                return redirect('/')

    if 'user' in session: session.pop('user')
    return render_template('login.html', title='Login')





@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')





@app.route('/profile')
def profile():
    user = User.query.get(session['user']['id'])
    return render_template('profile.html', title=session['user']['name'], user=user)





@app.route('/users/new', methods=['GET', 'POST'])
def new_user():
    if not session['user']['admin']: return redirect('/profile')

    if 'submit' in request.form:
        name     = request.form['name']     if request.form['name']     else None 
        username = request.form['username'] if request.form['username'] else None
        temp_pw  = pwd.genword(length=12, charset='ascii_50')

        if name and username:
            duplicate = User.query.filter_by(username=username).count()
            
            if not duplicate:
                user = User(name=name, username=username, temp_pw=temp_pw, password=None, selected_sprint_id=None)

                db.session.add(user)
                db.session.commit()
                return redirect('/users')

    return render_template('edit-user.html', title='New User')





@app.route('/users/<int:id>/reset')
def reset_password(id):
    if not session['user']['admin']: return redirect('/profile')

    user = User.query.get(id)

    user.temp_pw  = pwd.genword(length=12, charset='ascii_50')
    user.password = None
    db.session.commit()

    return redirect('/users')





@app.route('/users/<int:id>/change', methods=['GET', 'POST'])
def change_password(id):
    user = User.query.get(id)

    if 'submit' in request.form:
        old_pw = request.form['old'].strip() if request.form['old'] else None 
        new_pw = request.form['new'].strip() if request.form['new'] else None

        auth = False

        if old_pw and new_pw:
            if user.temp_pw:
                if old_pw == user.temp_pw: auth = True
            elif user.password:
                if hash.pbkdf2_sha256.verify(old_pw, user.password): auth = True

        if auth:
            if valid_password(new_pw):
                user.password = hash.pbkdf2_sha256.encrypt(new_pw)
                user.temp_pw  = None
                if 'change_pw' in session: del session['change_pw']

                db.session.commit()
                return redirect('/profile')

    return render_template('change-pw.html', title='Change Password', user=user)





def valid_password(pw):
    letters = 'abcdefghijklmnopqrstuvwxyz'
    numbers = '01234656789'
    symbols = '!-@#$%^&*(=)?+'

    min_len = 6
    max_len = 20
    min_ltr = 1
    min_num = 1
    min_sym = 0

    n_ltr = 0
    n_num = 0
    n_sym = 0

    for ch in pw.lower():
        if ch in letters: n_ltr = n_ltr + 1
        if ch in numbers: n_num = n_num + 1
        if ch in symbols: n_sym = n_sym + 1

    length = len(pw)

    r_len = True if length > min_len - 1 and length < max_len + 1 else False
    r_ltr = True if n_ltr >= min_ltr else False
    r_num = True if n_num >= min_num else False
    r_sym = True if n_sym >= min_sym else False
    r_chr = True if n_ltr + n_num + n_sym == length else False

    result = True if r_len and r_ltr and r_num and r_sym and r_chr else False
    return result





@app.route('/users/<int:id>/edit', methods=['GET', 'POST'])
def edit_user(id):
    if id != session['user']['id']:
        if not session['user']['admin']: return redirect('/profile')

    user = User.query.get(id)

    if 'submit' in request.form:
        name     = request.form['name']     if request.form['name']     else None 
        username = request.form['username'] if request.form['username'] else None

        if name and username:
            duplicate = User.query.filter_by(username=username).count()
            
            if not duplicate:
                user.name     = name
                user.username = username

                db.session.commit()
                return redirect('/users')

    return render_template('edit-user.html', title='Edit User', user=user)





@app.route('/users')
def users():
    if not session['user']['admin']: return redirect('/profile')

    users = User.query.all()
    return render_template('users.html', title='Users', users=users)





@app.route('/users/<int:id>/delete', methods=['GET', 'POST'])
def delete_user(id):
    if not session['user']['admin']: return redirect('/profile')

    user = User.query.get(id)

    if 'submit' in request.form:
        db.session.delete(user)
        db.session.commit()
        return redirect('/users')

    return render_template('delete.html', title=user.name, type='User', cancel='/users')





if __name__ == '__main__':
	app.run()