# gxbzys
实现视频加密、解密以及播放

## 加密视频文件结构
|  名字 |说明|长度|实现|
| ------------ |------------ |------------ |------------ |
|视频文件头|包含文件标记、文件信息索引、加密视频文件块索引|不定长|`VideoHead` `VideoInfoIndex` `VideoContentIndex`|
|视频文件信息| 文件信息，可以包含多个文件信息|不定长 |`VideoInfo`|
|加密视频文件块| 包含多个加密文件块 |文件块长度可以指定，在同一个加密视频中，文件块大小为指定大小或指定大小+16 bytes |`bytes`|

### `VideoHead`视频文件头
|  名字 |说明|长度|实现|
| ------------ |------------ |------------ |------------ |
| |文件标记|7个字节|`b'EV00001'`|
|head_size| 文件头内所有数据所占字节数|4个字节|`int`, `bytesorder='big'`|
|raw_file_size| 原始视频长度|5个字节|`int`, `bytesorder='big'`|
|video_info_index_size| 视频信息长度|5个字节|`int`, `bytesorder='big'`|
|video_info_index_cnt| 视频信息数量|2个字节|`int`, `bytesorder='big'`|
|video_info_index| 视频信息索引，可包含多个索引 |一个索引20个字节|`List[VideoInfoIndex]`|
|block_index| 加密视频索引，可包含多个索引 |一个索引32个字节|`List[VideoContentIndex]`|

#### `VideoInfoIndex` 视频信息索引 

|  名字 |说明|长度|实现|
| ------------ |------------ |------------ |------------ |
|length|视频信息加密数据块包含的数据数量|4个字节|`int`, `bytesorder='big'`|
|iv|偏移向量|16个字节|`bytes`|

#### `VideoContentIndex` 加密视频文件块索引

|  名字 |说明|长度|实现|
| ------------ |------------ |------------ |------------ |
|iv|加密使用的偏移向量|16个字节|`bytes`|
|start_pos|数据块在加密文件中的起始位置|5个字节|`int`, `bytesorder='big'`|
|raw_start_pos|数据块在原始文件中的起始位置|5个字节|`int`, `bytesorder='big'`|
|data_size|未加密的数据块大小| 3个字节 |`int`, `bytesorder='big'`|
|block_size|加密以后的数据块大小| 3个字节 |`int`, `bytesorder='big'`|

### `VideoInfo`视频信息加密数据块数据

|  名字 |说明|长度|实现|
| ------------ |------------ |------------ |------------ |
|video_info_cnt|信息块包含的数据数量（name,data）|2个字节|`int`, `bytesorder='big'`|
|info|内部包含一组或多组name,data数据|不定长|`Dict[bytes, Union[bytes, BytesIO, FileIO]]`|

#### `VideoInfo.info` 
|  名字 |说明|长度|实现|
| ------------ |------------ |------------ |------------ |
|name|名字，右补b'\0'|1024个字节|`bytes`|
|data_len|数据长度|3个字节|`int`, `bytesorder='big'`|
|data|数据|data_len|`bytes`|

### 加密视频文件块
|  文件块 |说明|
| ------------ |------------ |
|数据块|长度一般为1M|
|填充字符| |

### 字节长度表
最大值 = `pow(2, 字节长度 * 8) - 1'

|  字节长度 |最大值|
| ------------ |------------ |
|2|64KB - 1B|
|3|16MB - 1B|
|4|4GB - 1B|
|5|1TB - 1B|
