/**
 * Eric The Fish
 * ~~~~~~~~~~~~~
 *
 * This file now adds the fish to the admin panel. It basically creates a
 * new div for the fish and a second one for the bubble. Then it assigns some
 * classes and registeres a click action for the fish that sends a request.
 *
 * :copyright: (c) 2008 by the Zine Team, see AUTHORS for more details.
 * :license: BSD, see LICENSE for more details.
 */

/* execute all the following code during the document setup in a closure.
   all the variables defined in this function are local so we don't leak
   anything. */
$(function() {
  /* create erics div and add a click action */
  var eric = $('<div class="eric-the-fish">').click(function() {
    /* if the fish is not visible get one quote from the server */
    if (bubble.css('display') == 'none') {
      /* zine provides a function called `callJSONService` that
         is used to call the json endpoint of a service point and return
         the value parsed. */
      Zine.callJSONService('eric_the_fish/get_fortune', {}, function(q) {
        /* when the data comes back add the text to the bubble data */
        bubble_data.text(q.fortune);
        /* and fade the bubble slowly in */
        bubble.fadeIn('fast');
      });
    }
    /* clicking on a visible bubble fades it out */
    else
      bubble.fadeOut('slow');
  /* and then add the css class for the current skin */
  }).addClass('eric-in-' + $ERIC_THE_FISH_SKIN);

  /* now create the bubble and data and attach all to the body */
  var bubble = $('<div class="erics-bubble">').hide();
  var bubble_data = $('<div class="bubble-data">').appendTo(bubble);
  $('body').append(eric).append(bubble);
});
