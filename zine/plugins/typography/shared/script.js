/**
 * Typography Script
 * ~~~~~~~~~~~~~~~~~
 *
 * show a small popup with useful chars if a user clicks on one of
 * the special text boxes with quotes etc.
 *
 * :copyright: 2007 by Armin Ronacher.
 * :license: GNU GPL.
 */

var $active_field = null;

$(function() {
  $('form dd input').focus(function() {
    $active_field = $(this);
    $('#char-select').fadeIn('fast');
  }).blur(function() {
    $('#char-select').fadeOut('fast');
  });
});

function insertChar(char) {
  if ($active_field)
    $active_field.val(char);
}
