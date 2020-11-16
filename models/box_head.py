# Modified from ultralytics/yolov5 by Zhiqiang Wang
import torch
from torch import nn, Tensor
from torch.jit.annotations import Tuple, List, Dict, Optional
from torchvision.ops import batched_nms

from . import _utils as det_utils


class YoloHead(nn.Module):
    def __init__(self, in_channels, num_anchors, strides, num_classes):  # detection layer
        super().__init__()
        self.num_anchors = num_anchors  # anchors
        self.num_classes = num_classes
        self.num_outputs = num_classes + 5  # number of outputs per anchor
        self.strides = strides

        self.head = nn.ModuleList(
            nn.Conv2d(ch, self.num_outputs * self.num_anchors, 1) for ch in in_channels)  # output conv

        # Init weights, biases
        self._initialize_biases()

    def get_result_from_head(self, features: Tensor, idx: int) -> Tensor:
        """
        This is equivalent to self.head[idx](features),
        but torchscript doesn't support this yet
        """
        num_blocks = 0
        for m in self.head:
            num_blocks += 1
        if idx < 0:
            idx += num_blocks
        i = 0
        out = features
        for module in self.head:
            if i == idx:
                out = module(features)
            i += 1
        return out

    def forward(self, x: List[Tensor]) -> Tensor:
        all_pred_logits = torch.jit.annotate(List[Tensor], [])  # inference output

        for i, features in enumerate(x):
            pred_logits = self.get_result_from_head(features, i)

            # Permute output from (N, A * K, H, W) to (N, HWA, K)
            N, _, H, W = pred_logits.shape
            pred_logits = pred_logits.view(N, self.num_anchors, -1, H, W)
            pred_logits = pred_logits.permute(0, 1, 3, 4, 2)
            pred_logits = pred_logits.reshape(N, -1, self.num_outputs)  # Size=(N, HWA, K)

            all_pred_logits.append(pred_logits)

        return torch.cat(all_pred_logits, dim=1)

    def _initialize_biases(self, cf=None):
        # https://arxiv.org/abs/1708.02002 section 3.3
        # cf is class frequency
        # cf = torch.bincount(torch.tensor(
        #     np.concatenate(dataset.labels, 0)[:, 0]).long(), minlength=nc) + 1.
        for m, s in zip(self.head, self.strides):
            b = m.bias.view(self.num_anchors, -1)  # conv.bias(255) to (3,85)
            b[:, 4] += torch.log(torch.tensor(8 / (640 / s) ** 2))  # obj (8 objects per 640 image)
            b[:, 5:] += torch.log(torch.tensor(
                0.6 / (self.num_classes - 0.99))) if cf is None else torch.log(cf / cf.sum())
            m.bias = nn.Parameter(b.view(-1), requires_grad=True)


class PostProcess(nn.Module):
    __annotations__ = {
        'box_coder': det_utils.BoxCoder,
    }
    """Performs Non-Maximum Suppression (NMS) on inference results"""
    def __init__(
        self,
        score_thresh: float,
        nms_thresh: float,
        detections_per_img: int,
    ):
        super().__init__()
        self.box_coder = det_utils.BoxCoder()
        self.score_thresh = score_thresh
        self.nms_thresh = nms_thresh
        self.detections_per_img = detections_per_img  # maximum number of detections per image

    def forward(
        self,
        head_outputs: Tensor,
        anchors_tuple: Tuple[Tensor, Tensor, Tensor],
        image_shapes: Optional[List[Tuple[int, int]]] = None,
    ) -> List[Dict[str, Tensor]]:
        """ Perform the computation. At test time, postprocess_detections is the final layer of YOLO.
        Decode location preds, apply non-maximum suppression to location predictions based on conf
        scores and threshold to a detections_per_img number of output predictions for both confidence
        score and locations.

        Parameters:
            head_outputs : [batch_size, num_anchors, num_classes + 5] predicted locations and class/object confidence.
            image_shapes: tensor of dimension [batch_size x 2] containing the size of each images of the batch
                          For evaluation, this must be the original image size (before any data augmentation)
                          For visualization, this should be the image size after data augment, but before padding
        """
        num_images = len(image_shapes)
        detections = torch.jit.annotate(List[Dict[str, Tensor]], [])

        for index in range(num_images):  # image index, image inference
            pred_logits = torch.sigmoid(head_outputs[index])

            # Compute conf
            # box_conf x class_conf, w/ shape: num_anchors x num_classes
            scores = pred_logits[:, 5:] * pred_logits[:, 4:5]

            boxes = self.box_coder.decode_single(pred_logits[:, :4], anchors_tuple)

            # remove low scoring boxes
            inds, labels = torch.where(scores > self.score_thresh)
            boxes, scores = boxes[inds], scores[inds, labels]

            # non-maximum suppression, independently done per level
            keep = batched_nms(boxes, scores, labels, self.nms_thresh)
            # keep only topk scoring head_outputs
            keep = keep[:self.detections_per_img]
            boxes, scores, labels = boxes[keep], scores[keep], labels[keep]

            detections.append({'scores': scores, 'labels': labels, 'boxes': boxes})

        return detections
