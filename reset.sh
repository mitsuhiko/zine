#!/bin/bash

rm -rf instance/
mkdir instance
python -c "
from sqlalchemy import create_engine
from textpress.database import users, init_database
from textpress.utils import gen_pwhash, gen_secret_key
from textpress.config import Configuration
e = create_engine('sqlite:///instance/database.db')
init_database(e)

cfg_fn = './instance/textpress.ini'
cfg = Configuration(cfg_fn)
cfg.update(
    maintenance_mode=False,
    blog_url='http://localhost:4000',
    secret_key=gen_secret_key(),
    database_uri='sqlite:///instance/datatabase.db'
)
cfg.save()
"
echo "Created initial configuration"
python textpress-management.py shell >> /dev/null <<EOF
from textpress.models import User
textpress.bind_to_thread()
a = User(u'admin', u'default', u'admin@example.com', role=4)
db.save(a)
db.commit()
EOF
echo "Created superuser 'admin:default'"

