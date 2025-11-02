import os
import atexit
from google.protobuf.message import DecodeError
from src.utils.lock_manager import LockManager
from src.utils.deal_proto import compile_proto, load_pb2_module


class ResourceManager:

    DataBaseVersion = 'v1.0'

    def __init__(self, name, proto_file):
        self.database_name = name
        self.lock_manager = LockManager()
        compile_proto(proto_file)
        self.module = load_pb2_module(proto_file)

        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)

        self.data_path = os.path.join(self.data_dir, f"{self.database_name}.bin")

        file_desc = self.module.DESCRIPTOR
        self.TableMsgName = None
        for msg_name, msg_desc in file_desc.message_types_by_name.items():
            if msg_desc.fields and msg_desc.fields[0].label == 3:
                self.TableMsgName = msg_name
                break
        TableClass = getattr(self.module, self.TableMsgName)
        self.table = TableClass()

        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "rb") as f:
                    self.table.ParseFromString(f.read())
                print(f"📂 Loaded existing DB: {self.data_path}")
            except DecodeError:
                print(f"⚠️ Corrupted DB file, initializing new table")
        else:
            print(f"🆕 New DB initialized: {self.database_name}")
        self.shadow_tables = {}
        self.write_sets = {}
        self.tx_states = {}
        self.shadow_file = lambda xid: os.path.join(self.data_dir, f"{self.database_name}_{xid}.tmp")

        atexit.register(self._save_on_exit)

    def _save_on_exit(self):
        with open(self.data_path, "wb") as f:
            f.write(self.table.SerializeToString())
        print(f"💾 Auto-saved DB → {self.data_path}")

    def _write_shadow_to_disk(self, xid):
        """将影子页持久化保存到磁盘"""
        filename = self.shadow_file(xid)
        with open(filename, "wb") as f:
            f.write(self.shadow_tables[xid].SerializeToString())


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
            f.write(self.table.SerializeToString())
        print(f"✅ Saved to file: {filename}")

    def LoadFromFile(self, filename):
        with open(filename, "rb") as f:
            self.table.ParseFromString(f.read())
        print(f"✅ Loaded from file: {filename}")

    def prepare(self, xid):
        if not self._check_consistency(xid):
            return False
        self._write_shadow_to_disk(xid)
        self.tx_states[xid] = "PREPARED"
        return True
    
    def commit(self, xid):
        if xid not in self.tx_states or self.tx_states[xid] != "PREPARED":
            print(f"⚠️ xid={xid} 未处于 PREPARED 状态，强制提交")
        
        # ✅ 从 shadow_table 变成正式主表
        self.table = self.shadow_tables[xid]

        # ✅ 覆盖主数据写盘
        self.ToFile(self.data_path)

        # ✅ 清理锁与事务缓存
        self.lock_manager.release_locks(xid)
        del self.shadow_tables[xid]
        del self.write_sets[xid]
        del self.tx_states[xid]

        # ✅ 删除 shadow 临时文件
        sf = self.shadow_file(xid)
        if os.path.exists(sf):
            os.remove(sf)

        print(f"✅ COMMITTED xid={xid}")
        return True
    
    def abort(self, xid):
        if xid in self.shadow_tables:
            del self.shadow_tables[xid]
        if xid in self.write_sets:
            del self.write_sets[xid]
        if xid in self.tx_states:
            del self.tx_states[xid]

        self.lock_manager.release_locks(xid)

        # ✅ 删除未提交磁盘影子文件
        sf = self.shadow_file(xid)
        if os.path.exists(sf):
            os.remove(sf)

        print(f"❌ ABORTED xid={xid}")
        return True
    
    def recover(self):
        for filename in os.listdir(self.data_dir):
            if filename.endswith(".tmp"):
                xid = filename.split("_")[-1].split(".")[0]
                self.tx_states[xid] = "PREPARED"
                print(f"⚠️ 未完成事务残留，需要 TM 判决: xid={xid}")

   
