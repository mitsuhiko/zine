/**
 * TextPress Administration Tools
 * ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
 *
 * Part of the TextPress core framework. Provides default script
 * functions for the administration interface.
 *
 * :copyright: 2007-2008 by Armin Ronacher.
 * :license: GNU GPL.
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
    if ($(this).is('.collapsed'))
      children.hide();
    $('h3', this).click(function() {
      children.toggle();
      fieldset.toggleClass('collapsed');
    });
  });
});


/**
 * helper for upload forms with a progress bar
 */
UploadProgressBar = function(container, transportID, readyMessage) {
  this.container = $(container);
  this.transportID = transportID;
  this.bar = $('<div class="bar">').appendTo(this.container);
  this.label = $('<div class="label">').appendTo(this.container);
  this.oldPercent = 0;
  this.readyMessage = readyMessage || _('Finishing upload, stand by....');
};

UploadProgressBar.prototype.connectTo = function(form) {
  var self = this;
  this.bar.css('width', '0px');
  $(form).submit(function() {
    self.container.fadeIn('slow');
    self.label.text(_('Starting upload...'));
    window.setTimeout(function updateStatus() {
      data = {upload_id: self.transportID};
      TextPress.callJSONService('get_upload_info', data, function(u) {
        // it could happen that the server clears the status before we
        // can pull it. so we have a test for percentages of over 95%
        if (!u.error || self.oldPercent > 95) {
          var percent = Math.round(100 / u.length * u.pos);
          if (percent == 100 || u.error) {
            self.bar.css('width', '100%');
            return self.label.text(self.readyMessage);
          }
          self.label.text(percent + '%');
          self.bar.css('width', percent + '%');
          self.oldPercent = percent;
        }
        window.setTimeout(updateStatus, 2000);
  })}, 2000)});
};
