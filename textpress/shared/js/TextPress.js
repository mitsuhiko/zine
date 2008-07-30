/**
 * Default TextPress JavaScript Driver File
 * ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
 *
 * Part of the TextPress core framework. Provides default script
 * functions for the base templates.
 *
 * :copyright: 2007 by Armin Ronacher.
 * :license: GNU GPL.
 */

var TextPress = {
  TRANSLATIONS : {},
  PLURAL_EXPR : function(n) { return n == 1 ? 0 : 1; },
  LOCALE : 'unknown',

  getJSONServiceURL : function(identifier) {
    return this.BLOG_URL + '/_services/json/' + identifier;
  },

  callJSONService : function(identifier, values, callback) {
    $.getJSON(this.getJSONServiceURL(identifier), values, callback);
  },
  
  replyToComment : function(parent_id) {
    $('form.comments input[@name="parent"]').val(parent_id);
    $('#comment-message').hide();
    this.callJSONService('get_comment', {comment_id: parent_id}, function(c) {
      $('#comment-message')
        .addClass('info')
        .text(_('Replying to comment by %s.').replace('%s', c.author) + ' ')
        .append($('<a href="#">')
          .text(_('(Create as top level comment)'))
          .click(function() {
            TextPress.replyToNothing();
            return false;
          }))
      document.location = '#leave-reply';
      $('#comment-message').fadeIn();
    });
  },

  replyToNothing : function() {
    $('form.comments input[@name="parent"]').val('');
    $('#comment-message').fadeOut();
  },

  gettext : function(string) {
    var translated = TextPress.TRANSLATIONS[string];
    if (typeof translated == 'undefined')
      return string;
    return (typeof translated == 'string') ? translated : translated[0];
  },

  ngettext: function(singular, plural, n) {
    var translated = TextPress.TRANSLATIONS[singular];
    if (typeof translated == 'undefined')
      return (n == 1) ? singular : plural;
    return translated[TextPress.PLURALEXPR(n)];
  },

  addTranslations : function(catalog) {
    for (var key in catalog.messages)
      this.TRANSLATIONS[key] = catalog.messages[key];
    this.PLURAL_EXPR = new Function('n', 'return +(' + catalog.plural_expr + ')');
    this.LOCALE = catalog.locale;
  }
};

$(function() {
  $('#comment-message').hide();
});

// quick alias for translations
_ = TextPress.gettext;
