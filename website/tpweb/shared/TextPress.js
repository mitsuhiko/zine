/**
 * TextPress Website Scripts
 * ~~~~~~~~~~~~~~~~~~~~~~~~~
 *
 * Some scripts for the TextPress webpage.
 *
 * :copyright: 2007 by Armin Ronacher.
 * :license: GNU GPL.
 */

var tpweb = {
  
  /* make a list an animated feature list */
  animateFeatureList : function(node, timeout) {
    var features = $('li', node), idx = 0;
    $(features.hide()[0]).fadeIn('slow');
    window.setInterval(function() {
      $(features[idx])
        .animate({height: 'hide', opacity: 'hide'}, 'slow');
      $(features[idx = (idx + 1) % features.length])
        .animate({height: 'show', opacity: 'show'}, 'slow');
    }, timeout || 5000);
  },

  /* called on initializations */
  init : function() {

    /* add anchors to headlines */
    for (var i = 1; i <= 6; i++)
      for (var j = 0; j <= 1; j++)
        $('h' + i + (j == 1 ? ' a' : '') + '[@id]').each(function() {
          var anchor = $('<a class="anchor">¶</a>')
            .attr('href', '#' + $(this).attr('id'))
            .attr('title', 'Permalink to this headline')
            .appendTo(this);
        });
  }
};

$(function() {
  tpweb.init();
});
