#!/bin/zsh
# Render every frame in batches, each with a fresh browser, then encode.
cd "${0:A:h}"
for i in {1..15}; do
  node render.mjs video > "out/render_$i.log" 2>&1
  code=$?
  if grep -q "done, ffmpeg 0" "out/render_$i.log"; then echo "finished after $i runs -> out/annrakshak-launch.mp4"; exit 0; fi
  [[ $code -eq 3 ]] || { echo "run $i failed"; tail -5 "out/render_$i.log"; exit 1; }
done
echo "gave up after 15 runs"; exit 1
