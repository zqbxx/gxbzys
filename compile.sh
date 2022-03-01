#!/usr/bin/env bash
export output_name=gxbzys_$(date "+%Y%m%d%H%M%S")_win32
export output_dir=../$output_name
mkdir -p $output_dir/gxbzys
cp -R -u ./gxbzys $output_dir
cp -R -u ../key-manager/keymanager $output_dir
cp -R -u ./ico/*.ico $output_dir
cp -R -u YourPlayer.py $output_dir
cp -R -u mpv-1.dll $output_dir
cp -R -u plugin.json $output_dir
cp -R -u ./config $output_dir
cd $output_dir
python -m nuitka --mingw64 --show-progress --standalone --nofollow-import-to=pygments --nofollow-import-to=PIL --nofollow-import-to=pytest --nofollow-import-to=prompt_toolkit --nofollow-import-to=PyQt5 --include-package-data=qtawesome --include-package-data=qtmodern --plugin-enable=pyside6 --windows-icon-from-ico=your_player_2.ico --windows-disable-console ./YourPlayer.py
cp -R -u ./config $output_dir/YourPlayer.dist
cp -R -u mpv-1.dll $output_dir/YourPlayer.dist
cp -R -u plugin.json $output_dir/YourPlayer.dist