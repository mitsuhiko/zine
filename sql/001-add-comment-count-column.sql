-- Until we have migrations working you have to execute that yourself.

alter table posts add column comment_count integer after comments_enabled not null;
