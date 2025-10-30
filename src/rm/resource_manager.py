import os
import subprocess
from google.protobuf import descriptor_pb2
from grpc_tools import protoc
from importlib import util
import os
import atexit
from google.protobuf.message import DecodeError

def compile_proto(proto_path: str):
    out_dir = os.path.dirname(proto_path)
    result = protoc.main([
        "protoc",
        f"-I{out_dir}",
        f"--python_out={out_dir}",
        f"--grpc_python_out={out_dir}",
        proto_path,
    ])
    if result != 0:
        raise RuntimeError(f"protoc failed with status {result}")
    print(f"✅ Proto compiled: {proto_path}")

class ResourceManager:

    DataBaseVersion = 'v1.0'
    DataBaseName = None
    ProtoFile = None
    Data = None

    def __init__(self, name, proto_file):
        self.DataBaseName = name
        self.ProtoFile = proto_file
        compile_proto(proto_file)
        self.module = self._load_pb2_module(proto_file)

        # ✅ 创建数据目录
        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)

        # ✅ 数据文件路径
        self.data_path = os.path.join(self.data_dir, f"{self.DataBaseName}.bin")

        # ✅ 初始化表
        file_desc = self.module.DESCRIPTOR
        self.TableMsgName = None
        for msg_name, msg_desc in file_desc.message_types_by_name.items():
            if msg_desc.fields and msg_desc.fields[0].label == 3:
                self.TableMsgName = msg_name
                break

        TableClass = getattr(self.module, self.TableMsgName)
        self.Table = TableClass()

        self.auto_id = 0  # ✅ 自增 ID 计数器

        # ✅ 若已存在数据文件，自动加载并恢复 ID
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "rb") as f:
                    self.Table.ParseFromString(f.read())
                # ✅ 获取现有最大 key，用于自增恢复
                if self.Table.records:
                    self.auto_id = max(int(k) for k in self.Table.records.keys())
                print(f"📂 Loaded existing DB: {self.data_path}")
            except DecodeError:
                print(f"⚠️ Corrupted DB file, initializing new table")
        else:
            print(f"🆕 New DB initialized: {self.DataBaseName}")

        # ✅ 注册程序关闭自动保存
        atexit.register(self._save_on_exit)

    def _save_on_exit(self):
        with open(self.data_path, "wb") as f:
            f.write(self.Table.SerializeToString())
        print(f"💾 Auto-saved DB → {self.data_path}")

    def _load_pb2_module(self, proto_path):
        base = os.path.splitext(os.path.basename(proto_path))[0]
        module_name = base + "_pb2"
        module_path = os.path.join(os.path.dirname(proto_path), module_name + ".py")
        spec = util.spec_from_file_location(module_name, module_path)
        module = util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    
    def Info(self):
        module = self.module
        file_desc = module.DESCRIPTOR
        print(f"✅ Loaded Proto File: {file_desc.name}")
        for msg_name, msg_desc in file_desc.message_types_by_name.items():
            print(f"📌 Message: {msg_name}")
            for field in msg_desc.fields:
                print(f"  • Field: {field.name:<10} "
                    f"type={field.type} "
                    f"is_repeated={field.is_repeated} "
                    f"number={field.number}")
        print("")
                
    def ToFile(self, filename):
        with open(filename, "wb") as f:
            f.write(self.Table.SerializeToString())
        print(f"✅ Saved to file: {filename}")

    def LoadFromFile(self, filename):
        with open(filename, "rb") as f:
            self.Table.ParseFromString(f.read())
        print(f"✅ Loaded from file: {filename}")

    def Add(self, record):
        self.auto_id += 1
        key = self.auto_id

        # 需要创建子 message并 CopyFrom
        entry = self.Table.records.get_or_create(key)
        entry.CopyFrom(record)

        print(f"✅ Record added id={key}")
        return key

    def Get(self, key):
        return self.Table.records.get(key)

    def Update(self, key, new_record):
        if key in self.Table.records:
            self.Table.records[key] = new_record
            return True
        return False

    def Delete(self, key):
        if key in self.Table.records:
            del self.Table.records[key]
            return True
        return False

    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.ToFile(f"{self.DataBaseName}.bin")
        print(f"💾 Auto-saved On Exit: {self.DataBaseName}.bin")
