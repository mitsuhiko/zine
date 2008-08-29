:mod:`zine.database.db`
============================

.. module:: zine.database.db

This module is a virtual module that combines functions from SQLAlchemy,
the SQLAlchemy ORM module and Zine into one module that exports them
all on one object.  If you are used to SQLAlchemy all you have to know is
that all the important identifiers from the following objects are exposed:

-   `sqlalchemy`
-   `sqlalchemy.orm`
-   the public methods of a scoped session object

This page covers most of the public interface but it can't fully replace
the `SQLAlchemy documentation`_.

.. _SQLAlchemy documentation: http://www.sqlalchemy.org/docs/


Mapper Interface
----------------

.. autofunction:: get_engine

.. autofunction:: object_session

.. autofunction:: mapper

.. autoclass:: DatabaseManager
    :members:

    .. attribute:: model

        A reference to the model.


Session Interface
-----------------

.. function:: flush()

    Send pending modifications to the database.

.. function:: commit()

    Commit the current transaction in progress.
    
    If no transaction is in progress, this method raises an exception.
    
    If the :func:`begin` function was called on additional times subsequent to
    its first call, :func:`commit` will not actually commit, and instead pops
    an internal transaction off its internal stack of transactions.  Only when
    the "root" transaction is reached an actual database-level commit occur.

.. function:: rollback()

    Rollback the current transaction in progress.

.. function:: execute(clause[, params])

    Execute the given clause, using the current transaction (if any).
     
    Returns a proxy object to the execution's results.
     
    clause
        a clause element (i.e. select(), text(), etc.) or a string with an
        SQL statement to be executed
         
    params 
        a optional dictionary of bind parameters.

.. function:: save(instance)

    Add a transient (unsaved) instance to this session.  This is normally
    called automatically on new objects unless `_tp_no_save` is explicitly
    set to `False`.  For more details see :func:`mapper`.

.. function:: begin()

    Begin a new transaction.

.. function:: clear()

    Remove all object instances from the active session.

.. function:: refresh(instance[, attribute_names])

    Refresh the attributes on the given instance.
    
    When called, a query will be issued to the database which will refresh
    all attributes with their current value.
    
    Lazy-loaded relational attributes will remain lazily loaded, so that the
    instance-wide refresh operation will be followed immediately by the lazy
    load of that attribute.
    
    Eagerly-loaded relational attributes will eagerly load within the single
    refresh operation.
    
    The `attribute_names` argument is an iterable collection of attribute
    names indicating a subset of attributes to be refreshed.

.. function:: expire(self, instance[, attribute_names])

    Expire the attributes on the given instance.

    The instance's attributes are instrumented such that when an attribute
    is next accessed, a query will be issued to the database which will
    refresh all attributes with their current value.
    
    The `attribute_names` argument is an iterable collection of attribute
    names indicating a subset of attributes to be expired.

.. data:: session

    A scoped session object.  Usually you don't have to use this object
    unless an operation is required that is not exposed to the high level
    :mod:`~zine.database.db` module.

Description Units
-----------------

.. autoclass:: Table

.. autoclass:: Column

.. autoclass:: String

.. autoclass:: Text

.. autoclass:: Integer

.. autoclass:: Float

.. autoclass:: Boolean

.. autoclass:: ForeignKey
