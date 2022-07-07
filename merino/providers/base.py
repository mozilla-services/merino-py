class BaseProvider:
    
    def enabled_by_default(self) -> bool:
        return False

    def hidden(self) -> bool:
        return False

    def availability(self) -> str:
        if self.hidden():
            return "hidden"
        elif self.enabled_by_default():
            return "enabled_by_default"
        else:
            return "disabled_by_default"

class DefaultProvider(BaseProvider):

    def enabled_by_default(self) -> bool:
        return True

