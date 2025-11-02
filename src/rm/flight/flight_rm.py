from src.rm.resource_manager import ResourceManager

class FlightResourceManager(ResourceManager):

    def __init__(self, name, proto_file):
        super().__init__(name, proto_file)

    def _check_consistency(self, xid):
        ws = self.write_sets.get(xid, {})
        for key, rec in ws.items():
            if rec.numAvail < 0 or rec.numAvail > rec.numSeats:
                return False
        return True