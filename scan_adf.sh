#!/bin/bash
set -x

SCAN_DIRECTORY=${SCAN_DIRECTORY:-/scans}
PROCESSING_LOCKFILE=${SCAN_DIRECTORY}/.scanlock
touch "$PROCESSING_LOCKFILE"

# Acquire lock for scanning and processing
exec 4<"$PROCESSING_LOCKFILE"
flock 4

# Create the directory for the scan
pushd $SCAN_DIRECTORY
mkdir -p "$FILENAME"
pushd "$FILENAME"

SCAN_DEVICE_FLAG=""
if [ -n "$SCANNER_DEVICE" ]; then
    SCAN_DEVICE_FLAG=("-d" "$SCANNER_DEVICE")
fi

case "$SOURCE" in
    Flatbed|Slide|Negative)
        scanimage "${SCAN_DEVICE_FLAG[@]}" --mode "$MODE" --source "$SOURCE" --resolution "$RESOLUTION" \
            --format png -o "image-001.png" 2>>stderr.log 1>>stdout.log
        SCAN_RESULT=$?
        ;;
    *)
        scanadf "${SCAN_DEVICE_FLAG[@]}" --mode "$MODE" --source "$SOURCE" --resolution "$RESOLUTION" \
            2>>stderr.log 1>>stdout.log
        SCAN_RESULT=$?
        ;;
esac

# Check if scan produced any image files
IMAGE_COUNT=$(ls -1 image-*.png 2>/dev/null | wc -l)

if [ "$SCAN_RESULT" -ne 0 ] || [ "$IMAGE_COUNT" -eq 0 ]; then
    echo "Scan failed (exit code: $SCAN_RESULT, images: $IMAGE_COUNT)" >> stderr.log
    # Cleanup and exit without looping
    rm -f image* 2>/dev/null
    exec 4<&-
    popd
    popd
    exit 1
fi

# Convert to pdf using Pillow (avoids ImageMagick security policy issues)
python3 -c "
from PIL import Image
import os
import glob

images = sorted(glob.glob('image-*.png'))
if images:
    imgs = [Image.open(f) for f in images]
    imgs[0].save('$FILENAME.pdf', save_all=True, append_images=imgs[1:])
" 2>>stderr.log 1>>stdout.log

# Only run OCR if PDF was created
if [ -f "$FILENAME.pdf" ]; then
    ocrmypdf -r -d -c --rotate-pages-threshold 0 "$FILENAME.pdf" "$FILENAME.ocr.pdf" 2>>stderr.log 1>>stdout.log
    # Sometimes ocrmypdf still has these files locked after, wait until they're done
    until ! lsof "stdout.log" >/dev/null 2>&1; do sleep 1s; done
    until ! lsof "stderr.log" >/dev/null 2>&1; do sleep 1s; done
    mv "$FILENAME.ocr.pdf" "$FILENAME.pdf" 2>>stderr.log 1>>stdout.log
fi

# Cleanup image files
rm image* 2>>stderr.log 1>>stdout.log

# Ensure permissions allow users to access the scans
chmod -R u+rwX,g+rwX,o+rwX "$FILENAME"

# Short delay between scan jobs
sleep 5s

exec 4<&- 
popd # FILENAME

popd # SCAN_DIRECTORY
