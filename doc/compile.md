Windows下编译
---

- 打开git-bash，进入 `工作目录`
    ```bash
    git clone https://github.com/zqbxx/gxbzys.git
    git clone https://github.com/zqbxx/key-manager.git
    ```

- 下载libmpv

    https://sourceforge.net/projects/mpv-player-windows/files/libmpv/
    
    解压下载的压缩包，将`mpv-1.dll`复制到 `工作目录/gxbzys` 下

- 编译
    ```bash
    cd gxbzys
    pip install -r requirements.txt
    ./compile.sh
    ```