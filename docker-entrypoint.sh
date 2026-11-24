#!/bin/sh
# Har ishga tushganda yt-dlp va gallery-dl yangilanadi (AUTO_UPDATE=0 bilan o'chiriladi)
if [ "${AUTO_UPDATE:-1}" = "1" ]; then
    echo "yt-dlp va gallery-dl yangilanmoqda..."
    pip install -q -U "yt-dlp[default]" gallery-dl || echo "Yangilab bo'lmadi, mavjud versiya bilan davom etamiz"
fi
exec python -m savebot
