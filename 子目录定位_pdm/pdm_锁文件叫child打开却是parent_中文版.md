# 锁文件里叫 child，打开却是 parent

锁文件里的名字还是 `child`。归档的哈希也没变。

可把这份文件重新读进来，准备项目元数据，读到的却是 `parent`，依赖也从 `child-dep` 换成了 `parent-dep`。

这不是一个包改了名字。它们是同一个 ZIP 里的两个项目：一个在根目录，一个在子目录。**文件没有拿错，文件里面的项目却选错了。**

这是十月最后一周里，同一段导出路线上补的第三处。第一处是 [PDM #3954](https://github.com/pdm-project/pdm/pull/3954)，10 月 24 日提出，25 日凌晨合并，管入口——归档 URL 里的 `#subdirectory=...` 能不能进到 requirement 里。第二处是 #3956，25 日提出，27 日凌晨合并，管读入端——锁文件里的归档哈希别在重新打开时丢掉；上一篇[《锁文件里明明有哈希，PDM 为什么说没有？》](../锁文件哈希_pdm/pdm_锁文件里的哈希去哪了_中文版.md)写的就是它。

第三处是 [PDM #3964](https://github.com/pdm-project/pdm/pull/3964)。28 日提出，29 日 12:04:27 批准，12:04:38 合并，中间隔了十一秒。生产代码两行。要看出这两行为什么省不掉，得把已经修过的入口、一次成功的导出，以及导出之后的重新读取，按它们发生的顺序连起来看。（日期都按 GitHub 记录的 UTC。）

## 一、入口这一站，几天前刚修过

归档里有三个项目：根目录的 `parent`，子目录 `src/a&b` 里的 `child`，另放一个 `src/a` 里的 `decoy`。它们各自声明不同的依赖，才看得出实际读到了谁；普通目录的对照，把同一个 child 放在 `src/child`。

要用的不是解压后随便哪个 `pyproject.toml`，而是明确指到子目录的那个：

```text
child @ file:///.../bundle.zip#subdirectory=src/a%26b
```

这里的 `%26` 不是装饰。归档 requirement 的 fragment 由 [`parse_qsl()`](https://github.com/pdm-project/pdm/blob/f01b85810baacec4c8a22168da3f9e54550adb14/src/pdm/models/requirements.py#L403-L407) 读入：先按 `&` 拆成键值对，再对每个值做百分号解码。目录名里的 `&` 原样写进去，就会在自己身上断成两条参数，剩下的 `src/a` 恰好是归档里那个 `decoy` 的目录；写成 `%26`，它才是数据。

![同一个 & 的两种身份：写成 %26 时 fragment 只有一个参数，解码后是 src/a&b；直接写 & 时在同一处断成两条参数，只剩 src/a](assets/fig2_subdirectory_encoding.png)

补的正是这一站的，是 #3954。它让归档 requirement 从 URL fragment 里取出 `subdirectory`，再次生成链接时也带着它；对于未显式命名、带子目录的归档，不再先从外层文件名猜项目名，而是把名字交给所选目录的元数据。

再次生成链接这一环也要紧，因为 requirements 导入不是把一行原文原封不动藏起来。[导入函数](https://github.com/pdm-project/pdm/blob/f01b85810baacec4c8a22168da3f9e54550adb14/src/pdm/formats/requirements.py#L199-L214)会先解析，再调用 `as_line()` 输出依赖。只在第一次解析时记得子目录，下一次写出仍然可能丢掉。

[#3954 的回归测试](https://github.com/pdm-project/pdm/blob/f41b4e7c0d12ca9a171470beb1f3bc96a4a0233d/tests/models/test_candidates.py#L74-L110)已经把 parent、child、decoy 放进同一个归档，检查选中的依赖来自 child，普通 PDM 锁记录也带着子目录。

入口这一站通了。可从「能读对」到「换成另一种锁文件格式以后还能读对」，中间还隔着一道出口。

## 二、导出成功，为什么还不够？

反例是 #3964 自己记下的，很具体：先 `pdm add --no-sync`，再 `pdm export -f pylock`，导出记录仍叫 child；把导出结果重新读入，准备出来的元数据却来自 parent。

命令没报错，名字也没变。光是导出成功、`name = "child"`，这次往返看着就该算成功。

问题在归档记录里。修复前的包记录长这样（等价节选，省掉 pylock 文件头与其他字段，下载地址和哈希也做了缩写）：

```toml
[[packages]]
name = "child"
version = "1.0"

[packages.archive]
url = "file:///.../bundle.zip"

[packages.archive.hashes]
sha256 = "…"
```

名字有了，文件有了，哈希也有了，唯独没说 child 在 ZIP 的哪里。

内存里的 requirement 一直带着 `subdirectory`。可[父提交的 pylock 写出器](https://github.com/pdm-project/pdm/blob/7aaeb992092d827dee173e60e82cfffa0a5b9676/src/pdm/formats/pylock.py#L33-L69)的 archive 分支只写了下载 URL、可选路径和哈希——这个独立的属性没写出去。

容易走岔的地方也在这里：URL 里的 fragment 确实没了，看着最直接的修法就是把 `#subdirectory=...` 留下。

但 [`get_full_url()`](https://github.com/pdm-project/pdm/blob/f01b85810baacec4c8a22168da3f9e54550adb14/src/pdm/models/requirements.py#L372-L407) 去掉 fragment，并不是这次要推翻的选择。下载地址说的是取哪一个归档；从归档里挑哪个项目，pylock 有自己的 `archive.subdirectory` 字段。不能因为 URL 不再带选择器，就让选择器从记录里彻底消失。

**丢掉的不是下载地址的一段尾巴，而是一次格式转换没有接住的项目位置。**

## 三、哈希正确，恰好无法替它作证

上一篇的问题，是文件里的哈希在读入时没有恢复。这次要看的两个版本，都已经包含那个读入修复：哈希完整保留，子目录照样可能不见。

几个 PR 不能各讲各的，原因就在这——它们接通的是同一条路线上的不同站。

| 修复 | 接通了哪一段 | 不能代替什么 |
|---|---|---|
| #3954 | 归档 URL 中的子目录进入 requirement，生成链接和普通 PDM 锁记录时继续保留 | 不负责 pylock archive 分支的写出 |
| #3956 | 读取 pylock 时，把 archive 哈希恢复到 candidate | 不负责保存项目目录 |
| #3964 | 写 pylock 时，把 requirement 的子目录写进 archive 表 | 不重做前两项已经接通的入口和哈希读取 |

这层关系是 [#3964 原文](https://github.com/pdm-project/pdm/pull/3964)自己交代的，其中一句：

> “Neither wrote `archive.subdirectory` in the pylock converter.”

前两项都没有在 pylock 转换器里写出这个字段。不是同一个补丁反复没修好，是同一份信息换一种表示，每一站都得有人接手。

一个 ZIP 完全可以包含多个 `pyproject.toml`。选 parent、选 child、选 decoy，归档字节都可以一模一样。SHA-256 只能核对拿到的是否仍是这份归档，补不出「进哪个目录」这个选择。

![同一份 bundle.zip 里的三个项目：archive 记录不带选择器时重新解包落在根目录，带 subdirectory 时落在 src/a&b](assets/fig1_archive_selection.png)

所以哈希相同不是这个反例里的矛盾，反倒是最要紧的条件：文件一直没换过，换掉的是解释它时站在哪个目录。

## 四、两行补丁，接回的不是包名

最终的[修复](https://github.com/pdm-project/pdm/blob/f01b85810baacec4c8a22168da3f9e54550adb14/src/pdm/formats/pylock.py#L60-L69)加在 archive 分支：

```python
if req.subdirectory:
    archive["subdirectory"] = req.subdirectory
```

有子目录就写，没有就不加字段。同一个函数里，VCS 和 directory 两个分支早就这么留着自己的子目录，archive 缺的只是这一步。

写出去的值是实际目录 `src/a&b`，不是 URL fragment 中的 `src/a%26b`。URL 编码属于把选择器放进链接时的表示；到了结构化字段里，该存的是解码后的路径。pylock [对 archive 子目录的定义](https://github.com/pypa/packaging.python.org/blob/8c6552668b7ff550de1a4a207ea21925703fba26/source/specifications/pylock-toml.rst#L516-L521)转引了 [VCS 子目录规则](https://github.com/pypa/packaging.python.org/blob/8c6552668b7ff550de1a4a207ea21925703fba26/source/specifications/pylock-toml.rst#L356-L368)：它指出源码树中项目根的位置。

补上以后，字段落在 `packages.archive` 表里，和 URL、hashes 平级：

```toml
[packages.archive]
url = "file:///.../bundle.zip"
subdirectory = "src/a&b"
# hashes 沿用原值
```

包名不用改。哈希不用重算，下载 URL 也不用把 fragment 拼回去。要恢复的是下次打开这份归档时进哪个目录。

[pylock 读入器](https://github.com/pdm-project/pdm/blob/f01b85810baacec4c8a22168da3f9e54550adb14/src/pdm/models/repositories/lock.py#L141-L148)本来就会读 `archive.subdirectory`，把它交回 requirement。不是 reader 不懂这个字段，是 writer 根本没给它写。

随后，[`as_file_link()`](https://github.com/pdm-project/pdm/blob/f01b85810baacec4c8a22168da3f9e54550adb14/src/pdm/models/requirements.py#L372-L379)把子目录重新放进安装链接；[`_unpack()`](https://github.com/pdm-project/pdm/blob/f01b85810baacec4c8a22168da3f9e54550adb14/src/pdm/models/candidates.py#L468-L491)交给解包器选目录；[`prepare_metadata()`](https://github.com/pdm-project/pdm/blob/f01b85810baacec4c8a22168da3f9e54550adb14/src/pdm/models/candidates.py#L511-L524)再从实际选中的路径读项目元数据。这才解释了开头那个看起来不可能的组合：记录里写着 child，元数据却来自 parent。名字来自锁文件，元数据来自后来真正打开的那个目录——两者不是同一次读取里的同一个事实。

## 五、换一次全新的读取，看它究竟打开谁

复现放在 [subdirectory_demo](subdirectory_demo/)，固定 #3964 的实际父提交与合并提交。两边都已经有 #3954 和 #3956，所以差出来的那一点，只能归到这次补的段上。

从同一份本地 ZIP 出发，用两份完整 PDM 源码分别跑 requirements 导入、候选元数据读取和 pylock 转换；序列化出来的 TOML 再交给新的 `LockedRepository`，看新 candidate 准备出来的元数据。写出前还记得子目录的旧对象，不算读回结果。

这次直接调用真实的导入器、转换器与读入器，省去完整 add 命令的依赖求解；`parent-dep` 这些名字只当元数据观察值，不去下载安装。输入分 URL 与本地路径两类：URL 场景由进程内 transport 提供同一份 ZIP 字节，不访问公网；执行期间禁止创建网络 socket。

两类来源各跑不指定目录、普通目录、含 `&` 目录三种场景，修前修后共 12 次重新读取元数据，另加两版 decoy 对照。URL / path 两组结果相同，合并展示；完整输出与环境见 [工程 README](subdirectory_demo/README.md)。

| 指定的子目录 | 修复前重新准备的项目 | 修复后重新准备的项目 |
|---|---|---|
| 不指定 | parent | parent |
| `src/child` | parent | child |
| `src/a&b` | parent | child |

两个指定子目录的场景，两边的导出记录都叫 child，归档哈希也相同；差的是修复前没有 `archive.subdirectory`，修复后原来的目录还在。含 `&` 的那组还得选中完整目录 `src/a&b`，不是诱饵 `src/a`。

上游[合并的回归测试](https://github.com/pdm-project/pdm/blob/f01b85810baacec4c8a22168da3f9e54550adb14/tests/test_formats.py#L1239-L1278)从 add、export 一路检查到新读回 candidate 的子目录属性；本文的复现多走一步，到元数据为止，观察 parent-dep 与 child-dep。准备元数据时，上游调用的是 `_unpack(validate_hashes=False)`；实验另外算 ZIP 的 SHA-256，核对导出和读回的哈希字段始终相同，看到元数据就停，不执行构建安装。

## 六、六天、三处，和最后那一站

10 月 24 日到 29 日，这条路上补了三处：入口、读入端的哈希、写出端的目录。每次改动都不大——这次两行——大的是它们在一条链上各自负责的那一段。

只看两行补丁，最容易把前后最值钱的部分压掉：入口已经修过，哈希也已经修过，导出照样能成功地把另一项信息丢掉。每一站单看都正常，重新打开归档，才发现拿到的已不是当初选的那个项目。

**往返保真的对象，不只是文件里的字符串，还包括下一次操作究竟会选中什么。**

上一篇补的是读入端：文件里有的信息，读回来时要恢复。这一篇补的是写出端：内存里知道的，写出去时要留下。两头都接住，锁文件才不只是看起来还像原来那份。

---

### 源码与复现

- 主修复：[PDM #3964](https://github.com/pdm-project/pdm/pull/3964)；前序关联 [#3954](https://github.com/pdm-project/pdm/pull/3954)、[#3956](https://github.com/pdm-project/pdm/pull/3956)。
- 合并日期（UTC）：#3954 2026-10-25、#3956 2026-10-27、#3964 2026-10-29。
- 修复前：[`7aaeb99`](https://github.com/pdm-project/pdm/tree/7aaeb992092d827dee173e60e82cfffa0a5b9676)；最终合并：[`f01b858`](https://github.com/pdm-project/pdm/tree/f01b85810baacec4c8a22168da3f9e54550adb14)。
- 离线对照与来源校验：[subdirectory_demo](subdirectory_demo/README.md)。本文观察到重新准备项目元数据为止，未执行包安装。
