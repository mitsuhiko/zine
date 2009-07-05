/**
 * Zine Administration Tools
 * ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
 *
 * Part of the Zine core framework. Provides default script
 * functions for the administration interface.
 *
 * :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
 * :license: BSD, see LICENSE for more details.
 */

$(function() {
  // fade in messages
  var messages = $('div.message').hide().fadeIn('slow');
  window.setTimeout(function() {
    messages.each(function() {
      if (!$(this).is('.message-error'))
        $(this).animate({height: 'hide', opacity: 'hide'}, 'slow');
    });
  }, 8000);

  // support for toggleable sections
  $('div.toggleable').each(function() {
    var
      fieldset = $(this),
      children = fieldset.children().slice(1);
    // collapse it if it should be collapsed and there are no errors in there
    if ($(this).is('.collapsed') && $('.errors', this).length == 0)
      children.hide();
    $('h3', this).click(function() {
      children.toggle();
      fieldset.toggleClass('collapsed');
    });
  });

  // Add bookmarklets to pages that want them
  (function() {
    var container = $('div.post-bookmarklets');
    if (!container.length)
      return;
    var
      bookmarkletURL = Zine.ADMIN_URL + '/_bookmarklet',
      bookmarklet = 'document.location.href="' + bookmarkletURL +
      '?mode=newpost&text="+encodeURI(getSelection?getSelection()' +
      ':document.getSelection?document.getSelection():document.' +
      'selection.createRange().text)+"&title="+encodeURI(document.' +
      'title)+"&url="+encodeURI(document.location.href)';
    container.append($('<h2>').text(_('Bookmarklet')));
    container.append($('<p>').text(
      _('Right click on the following link and choose ' +
        '“Add to favorites” or “Bookmark link” to create a ' +
        'posting shortcut.')));
    container.append($('<p>').text(
      _('Next time you visit an interesting page, just select some ' +
        'text and click on the bookmark.')));
    container.append($('<p>').append($('<a>')
      .attr('href', 'javascript:' + encodeURI(bookmarklet))
      .text(_('Blog It!'))
      .click(function() {
        alert(_('Right click on this link and choose “Add to ' +
                'favorites” or “Bookmark link” to create a ' +
                'posting shortcut.'));
        return false;
      })));
  })();

  // Tag support for the post editor.
  (function() {
    var tag_field = $("#f_tags");
    if (tag_field.length)
      Zine.callJSONService('get_taglist', {}, function(rv) {
        tag_field.autocomplete(rv.tags, {
          highlight: false,
          multiple: true,
          multipleSeparator: ", ",
          scroll: true,
          scrollHeight: 300
        });
      });
  })();

  // If we're on a new-post/edit-post page we can update the
  // page title dynamically based on the text field.
  (function() {
    var input_box = $('#post_form #f_title');
    if (input_box.length == 0)
      return;

    var title = document.title.split(/\u200B/, 2)[1];
    input_box.bind('change', function() {
      var arg = input_box.val();
      document.title = (arg ? arg + ' — ' : '') + title;
    });
  })();

  // Make some textareas resizable
  (function() {
    $('textarea.resizable').TextAreaResizer();
  })();
});
