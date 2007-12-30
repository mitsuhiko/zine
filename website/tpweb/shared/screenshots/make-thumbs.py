import os

for filename in os.listdir('.'):
    if filename.endswith('.png') and not filename.endswith('-thumb.png') \
       and not filename.endswith('-medium.png'):
        os.system('convert %s -resize 560 -sharpen 10 %s' % (
                  filename, filename[:-4] + '-medium.png'))
        os.system('convert %s -resize 180 -sharpen 10 %s' % (
                  filename, filename[:-4] + '-thumb.png'))
        print filename
