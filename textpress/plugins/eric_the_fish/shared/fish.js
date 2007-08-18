/**
 * Add a fish!!!
 */

$(document).ready(function() {
  var eric = $('<div class="eric-the-fish">').click(function() {
    if (bubble.css('display') == 'none') {
      TextPress.callJSONService('eric_the_fish/get_quote', {}, function(q) {
        if (q.error)
          bubble_data.text('Dammit. No fortune huh?');
        else
          bubble_data.text(q.quote);
        bubble.fadeIn('fast');
        window.setTimeout(function() { bubble.fadeOut('slow'); }, 10000);
      });
    }
    else
      bubble.fadeOut('slow');
  });
  var bubble = $('<div class="erics-bubble">').hide();
  var bubble_data = $('<div class="bubble-data">').appendTo(bubble);
  $('body').append(eric).append(bubble);
});
