"""Notifications subscription support"""
# Keep __doc__ to a single line
from zine.upgrades.versions import *

metadata = db.MetaData()

# Define tables here
users_old = db.Table('users', metadata,
    db.Column('user_id', db.Integer, primary_key=True),
    db.Column('username', db.String(30)),
    db.Column('real_name', db.String(180)),
    db.Column('display_name', db.String(180)),
    db.Column('description', db.Text),
    db.Column('extra', db.PickleType),
    db.Column('pw_hash', db.String(70)),
    db.Column('email', db.String(250)),
    db.Column('www', db.String(200)),
    db.Column('is_author', db.Boolean)
)

notification_subscriptions = db.Table('notification_subscriptions', metadata,
    db.Column('subscription_id', db.Integer, primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.user_id')),
    db.Column('notification_system', db.String(50)),
    db.Column('notification_id', db.String(100)),
    db.UniqueConstraint('user_id', 'notification_system', 'notification_id')
)

def upgrade(migrate_engine):
    # Upgrade operations go here. Don't create your own engine; use the engine
    # named 'migrate_engine' imported from migrate.
    log.info('<ul>')
    log.info(' <li>Create the notification subscriptions table</li>\n')
    log.info('</ul>')
    notification_subscriptions.create(migrate_engine)


def downgrade(migrate_engine):
    # Operations to reverse the above upgrade go here.
    log.info('<ul>')
    log.info(' <li>Drop the notification subscriptions table</li>\n')
    log.info('</ul>')
    notification_subscriptions.drop(migrate_engine)
