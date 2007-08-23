/**
 * File Uploads
 * ~~~~~~~~~~~~
 *
 * display the upload status in the ".uploadstatus" div.
 *
 * :copyright: 2007 by Armin Ronacher.
 * :license: GNU GPL.
 */

$(function() {
  var id = $TRANSPORT_ID,
      label = $('div.uploadstatus div.label'),
      bar = $('div.uploadstatus div.bar'),
      old_percent = 0;

  function updateStatus() {
    TextPress.callJSONService('get_upload_info', {upload_id: id}, function(u) {
      // it could happen that the server clears the status before we
      // can pull it. so we have a test for percentages of over 95%
      if (!u.error || old_percent > 95) {
        var percent = Math.round(100 / u.length * u.pos);
        if (percent == 100 || u.error) {
          bar.css('width', '100%');
          return label.text(_('Finishing upload, stand by...'));
        }
        label.text(percent + '%');
        bar.css('width', percent + '%');
        old_percent = percent;
      }
      window.setTimeout(updateStatus, 2000);
    });
  };

  if (id) $('form').submit(function() {
    $('div.uploadstatus').fadeIn('slow');
    bar.css('width', '0px');
    label.text(_('Starting upload...'));
    window.setTimeout(updateStatus, 4000);
  });
});
