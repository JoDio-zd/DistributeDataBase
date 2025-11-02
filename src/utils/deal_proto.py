from grpc_tools import protoc
from importlib import util
import os

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
        print(result)
        raise RuntimeError(f"protoc failed with status {result}")
    print(f"✅ Proto compiled: {proto_path}")

def load_pb2_module(self, proto_path):
        base = os.path.splitext(os.path.basename(proto_path))[0]
        module_name = base + "_pb2"
        module_path = os.path.join(os.path.dirname(proto_path), module_name + ".py")
        spec = util.spec_from_file_location(module_name, module_path)
        module = util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module