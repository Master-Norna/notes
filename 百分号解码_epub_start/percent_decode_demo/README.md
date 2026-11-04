# EPUB 资源路径解码复现

对应上游修复：[CaramelizedCUDA/epub-start#2](https://github.com/CaramelizedCUDA/epub-start/pull/2)
（合并提交 `a349b9e1e4bed5b927b6a9dd3da56cc5ed74d19f`，修前第一父 `ed7e300bfa894acc3854c2012db9e67a264bbd14`）。

`main.rs` 里有两版协议处理器的路径段：修前直接把 `request.uri().path()` 当 ZIP 条目名；修后先在入口调用 `decode_uri_path`。`normalize_entry_path` 与 ZIP 中央目录查找按上游实现提取，不启动 Tauri、不读数据库。

## 跑

需要 Rust（`rustc`）。`sample.epub` 已随附；要重新生成时用 Python 3：

```powershell
python make_sample.py
rustc -O main.rs -o epub_decode_demo.exe
./epub_decode_demo.exe --test
```

`--test` 会核对 9 个用例的状态码；不符合预期时退出码为 1。

## 输出

```
case               raw request path                                     before  after
CJK segments       book/7/OEBPS/%E5%9B%BE%E7%89%87/%E5%B0%81%E9%9D%A2.png    404    200
space              book/7/OEBPS/cover%20v2.png                             404    200
hash               book/7/OEBPS/a%23b.png                                  404    200
question           book/7/OEBPS/a%3Fb.png                                  404    200
percent            book/7/OEBPS/100%25.png                                 404    200
raw percent        book/7/OEBPS/100%.png                                   200    400
encoded dot-dot    book/7/%2E%2E/secret                                    404    403
invalid escape     book/7/OEBPS/%zz.png                                    404    400
plain path         book/7/OEBPS/chapter.xhtml                              200    200
```

实际输出见 `.yan/epub-percent/runs/epub-demo-publish-20261103.txt`。

## 文件

- `main.rs`：两版 handler、`decode_uri_path`、`normalize_entry_path`、ZIP 中央目录读取。
- `make_sample.py`：生成 `sample.epub`（8 个条目，`ZIP_STORED`）。
- `sample.epub`：含中文目录、空格、`#`、`?`、`%` 的条目名。
- `LICENSE`：上游 GPL-3.0 原文。

## 边界

- 不启动 Tauri/WebView，`book/<id>` 只校验非空。
- ZIP 只读中央目录的文件名，不解压内容。
- 请求路径由程序给出，模拟浏览器编码后的 URI path；没有让真实浏览器发请求。

上游代码以 GPL-3.0 发布，本目录的 `LICENSE` 为其原文。
