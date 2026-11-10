# danger worker 结果 pickle 复现（skylos #1200）

`_CallableIndex` 挂在 AST module 上，`Definition.node` 通过 `parent` 指针又能走回这个 module。函数作用域里的 flow 缓存保存了一个局部函数 `outer`，所以 worker 结果一 pickle 就抛：

```text
AttributeError: Can't get local object '_CallableIndex.flow.<locals>.outer'
```

`_drain_pool` 把它当成普通 worker 失败，调 `_retry_in_parent` 在父进程重算——文件被分析两次，多进程退化成串行，日志里只留一条 WARNING。

本工程取两版 `callable_bindings.py` 与 `flow_env.py`，构造同一个 fixture，直接 pickle 索引对象，对照父版与合并版。

## 运行

```console
python -B run.py --test
```

Python 3.11+，无第三方依赖。

## 目录

- `vendor/parent/callable_bindings.py`：父提交 `c05b6305c5fe5167d94d24c95f88c8891052a6a5` 的逐字拷贝。
- `vendor/merged/callable_bindings.py`：合并提交 `a10d85d31fbad2e4ad4c5059c3106c00625880fb` 的逐字拷贝。
- `vendor/*/flow_env.py`：上游同名文件的逐字拷贝（两版相同）。
- `vendor/*/import_proof.py`：桩。本工程只走 pickle 协议，不走 import 遮蔽判断，`provider_is_unshadowed` 返回 `False`。上游实现见对应提交的 `skylos/rules/danger/import_proof.py`。
- `vendor/LICENSE`：上游 Apache-2.0。

## 输出

`--test` 断言：

- 父版 `pickle.dumps(index)` 抛 `AttributeError`，消息里是 `_CallableIndex.flow.<locals>.outer`；
- 合并版 dump/load 成功，反序列化后 `_ready` 为 `False`、`flows` 还没建；
- 第一次 `scope()`/`flow()` 调用把 id 键的缓存从恢复出来的 module 重建，`os.system` 的识别结果不变。

完整包的进程池数字（20 个文件里父版 17 个退回父进程、合并版 0 个）需要用两版完整源码跑 `skylos.scale.parallel_static.run_proc_file_parallel` 才能得到；本工程不拉整套分析器，只复现跨进程边界上那一个对象。那组数字的复现脚本与输出留在仓库的检查记录里，不随本工程发布。
