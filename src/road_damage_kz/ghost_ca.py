"""Ghost-CA-YOLO support modules for Ultralytics models."""

from __future__ import annotations


def register_ultralytics_modules() -> None:
    """Expose custom modules to Ultralytics' YAML parser and model loader."""

    import ultralytics.nn.tasks as tasks

    CoordAtt.__module__ = "ultralytics.nn.tasks"
    setattr(tasks, "CoordAtt", CoordAtt)


class CoordAttModuleMixin:
    """Marker mixin for documentation and introspection."""


try:
    import torch
    from torch import nn
except ModuleNotFoundError:  # pragma: no cover - only needed in ML runtime
    torch = None
    nn = None


if nn is not None:

    class CoordAtt(nn.Module, CoordAttModuleMixin):
        """Coordinate Attention block.

        The block follows the efficient coordinate-attention design: it pools
        features separately along height and width, combines them through a
        compact bottleneck, and generates direction-aware attention maps.
        """

        def __init__(self, channels: int, reduction: int = 32) -> None:
            super().__init__()
            mip = max(8, channels // reduction)
            self.pool_h = nn.AdaptiveAvgPool2d((None, 1))
            self.pool_w = nn.AdaptiveAvgPool2d((1, None))
            self.conv1 = nn.Conv2d(channels, mip, kernel_size=1, stride=1, padding=0)
            self.bn1 = nn.BatchNorm2d(mip)
            self.act = nn.Hardswish()
            self.conv_h = nn.Conv2d(mip, channels, kernel_size=1, stride=1, padding=0)
            self.conv_w = nn.Conv2d(mip, channels, kernel_size=1, stride=1, padding=0)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            identity = x
            _, _, h, w = x.size()

            x_h = self.pool_h(x)
            x_w = self.pool_w(x).permute(0, 1, 3, 2)
            y = torch.cat([x_h, x_w], dim=2)
            y = self.act(self.bn1(self.conv1(y)))

            x_h, x_w = torch.split(y, [h, w], dim=2)
            x_w = x_w.permute(0, 1, 3, 2)
            a_h = self.conv_h(x_h).sigmoid()
            a_w = self.conv_w(x_w).sigmoid()
            return identity * a_h * a_w

else:  # pragma: no cover

    class CoordAtt(CoordAttModuleMixin):  # type: ignore[no-redef]
        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError("CoordAtt requires torch. Install the ML extras before training.")
