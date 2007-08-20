/**
 * TextPress Administration Tools
 * ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
 *
 * Part of the TextPress core framework. Provides default script
 * functions for the administration interface.
 *
 * :copyright: 2007 by Armin Ronacher.
 * :license: GNU GPL.
 */

$(function() {
  var messages = $('div.message').hide().fadeIn('slow');
  window.setTimeout(function() {
    messages.each(function() {
      if (!$(this).is('.message-error'))
        $(this).animate({height: 'hide', opacity: 'hide'}, 'slow');
    });
  }, 8000);
});
