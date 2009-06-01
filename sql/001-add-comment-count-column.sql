-- Until we have migrations working you have to execute that yourself.

alter table posts add column comment_count integer after comments_enabled not null;

-- We're missing a migration that splits texts and posts into the old
-- table contents and the new "texts" one.  Migrations should follow
-- soon.  Last revision with old tables is 198cd0bdbc05.
