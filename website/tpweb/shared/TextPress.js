/**
 * TextPress Website Scripts
 * ~~~~~~~~~~~~~~~~~~~~~~~~~
 *
 * Some scripts for the TextPress webpage.
 *
 * :copyright: 2007 by Armin Ronacher.
 * :license: GNU GPL.
 */

$(function() {

  /* add anchors to headlines */
  for (var i = 1; i <= 6; i++)
    $('h' + i + ' [@id]').each(function() {
      var anchor = $('<a class="anchor">¶</a>')
        .attr('href', '#' + $(this).attr('id'))
        .attr('title', 'Permalink to this headline')
        .appendTo(this);
    });
});
