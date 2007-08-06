/**
 * Default TextPress JavaScript Driver File
 * ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
 *
 * Part of the TextPress core framework. Provides default script
 * functions for the base templates.
 */

var TextPress = {
  TRANSLATIONS : {},

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
        .text('Replying to comment by ' + c.author + '.');
      document.location = '#leave-reply';
      $('#comment-message').fadeIn();
    });
  },

  gettext : function(string) {
    return this.TRANSLATIONS[string] || string;
  },

  addTranslations : function(translations) {
    for (var key in translations)
      this.TRANSLATIONS[key] = translations[key];
  }
};

// quick alias for translations
function _(string) { return TextPress.gettext(string); }
