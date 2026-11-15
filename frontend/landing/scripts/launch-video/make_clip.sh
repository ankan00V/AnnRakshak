#!/bin/zsh
# A 20-second "camera" clip for the live field check: eight ICAR false-smut
# photographs, each with a slow push-in, as a phone held over the crop would
# see them. out/clip/field_check.mp4 is uploaded on the laptop; the .y4m is
# Chrome's fake camera for the phone's video call.
set -e
HERE=${0:A:h}
SRC=${HERE}/../../../../data/processed/icar_640/rice_false_smut
OUT=$HERE/out/clip
mkdir -p $OUT
i=0
for f in $(ls $SRC/*.jpg | head -8); do
  ffmpeg -v error -y -loop 1 -i "$f" \
    -vf "scale=1280:960:force_original_aspect_ratio=increase,crop=1280:960,zoompan=z='min(zoom+0.0012,1.18)':d=38:s=640x480:fps=15,format=yuv420p" \
    -t 2.5 $OUT/seg_$i.mp4
  i=$((i+1))
done
(cd $OUT && ls seg_*.mp4 | sed "s/.*/file '&'/" > concat.txt)
ffmpeg -v error -y -f concat -safe 0 -i $OUT/concat.txt -c:v libx264 -pix_fmt yuv420p -r 15 $OUT/field_check.mp4
ffmpeg -v error -y -i $OUT/field_check.mp4 -pix_fmt yuv420p $OUT/fake_cam.y4m
rm -f $OUT/seg_*.mp4 $OUT/concat.txt
# A ninth photograph, for the laptop's photo upload.
cp "$(ls $SRC/*.jpg | sed -n 9p)" $OUT/upload.jpg
echo "clip: $OUT/field_check.mp4"
