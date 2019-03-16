#------------------------------------------------------------------------------
#	Libraries
#------------------------------------------------------------------------------
import cv2, torch, argparse
import numpy as np
from time import time
from torch.nn import functional as F

from models import UNet
from utils import utils


#------------------------------------------------------------------------------
#  Draw foreground pasted into background
#------------------------------------------------------------------------------
def draw_fore_to_back(image, mask, background, kernel_sz=13, sigma=0):
	mask_filtered = cv2.GaussianBlur(mask, (kernel_sz, kernel_sz), sigma)
	mask_filtered = np.expand_dims(mask_filtered, axis=2)
	mask_filtered = np.tile(mask_filtered, (1,1,3))
	image_alpha = image*mask_filtered + background*(1-mask_filtered)
	return image_alpha.astype(np.uint8)


#------------------------------------------------------------------------------
#   Argument parsing
#------------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="Arguments for the script")

parser.add_argument('--use_cuda', action='store_true', default=True,
                    help='Use GPU acceleration')

parser.add_argument('--bg', type=str, default=None,
                    help='Path to the background image file')

parser.add_argument('--img_layers', type=int, default=3,
                    help='Number of layers of the input image')

parser.add_argument('--input_sz', type=int, default=224,
                    help='Input size')

parser.add_argument('--checkpoint', type=str, default="model_best.pth",
                    help='Path to the trained model file')

args = parser.parse_args()


#------------------------------------------------------------------------------
#	Parameters
#------------------------------------------------------------------------------
# Video
cap = cv2.VideoCapture(0)
_, frame = cap.read()
H, W = frame.shape[:2]

# Background
if args.bg is not None:
	BACKGROUND = cv2.imread(args.bg)[...,::-1]
	BACKGROUND = cv2.resize(BACKGROUND, (W,H), interpolation=cv2.INTER_LINEAR)
	KERNEL_SZ = 25
	SIGMA = 0

# Alpha transperency
else:
	COLOR1 = [255, 0, 0]
	COLOR2 = [0, 0, 255]


#------------------------------------------------------------------------------
#	Main execution
#------------------------------------------------------------------------------
model = UNet(
    n_classes=1,
    img_layers=args.img_layers,
    backbone="ResNet",
    backbone_args={
        "n_layers": 18,
        "input_sz": args.input_sz,
        "pretrained": None,
    }
)
trained_dict = torch.load(args.checkpoint, map_location="cpu")['state_dict']
model.load_state_dict(trained_dict, strict=False)
if args.use_cuda:
	model = model.cuda()
model.eval()


# Predict frames
i = 0
while(cap.isOpened()):
	# Read frame from camera
	start_time = time()
	_, frame = cap.read()
	image = frame[...,::-1]
	h, w = image.shape[:2]
	read_cam_time = time()

	# Predict mask
	X, pad_up, pad_left, h_new, w_new = utils.preprocessing(image, expected_size=args.input_sz, pad_value=0)
	preproc_time = time()
	with torch.no_grad():
		if args.use_cuda:
			mask = model(X.cuda(), ret_sigmoid=False)
			mask = mask[..., pad_up: pad_up+h_new, pad_left: pad_left+w_new]
			mask = F.interpolate(mask, size=(h,w), mode='bilinear', align_corners=True)
			mask = torch.sigmoid(mask)
			mask = mask[0,0,...].cpu().numpy()
		else:
			mask = model(X, ret_sigmoid=False)
			mask = mask[..., pad_up: pad_up+h_new, pad_left: pad_left+w_new]
			mask = F.interpolate(mask, size=(h,w), mode='bilinear', align_corners=True)
			mask = torch.sigmoid(mask)
			mask = mask[0,0,...].numpy()
	predict_time = time()

	# Draw result
	if args.bg is None:
		# image_alpha = utils.draw_matting(image, mask)
		image_alpha = utils.draw_transperency(image, mask, COLOR1, COLOR2)
	else:
		image_alpha = utils.draw_fore_to_back(image, mask, BACKGROUND, kernel_sz=KERNEL_SZ, sigma=SIGMA)
	draw_time = time()

	# Wait for interupt
	cv2.imshow('webcam', image_alpha[..., ::-1])
	if cv2.waitKey(1) & 0xFF == ord('q'):
		break

	# Print runtime
	read = read_cam_time-start_time
	preproc = preproc_time-read_cam_time
	pred = predict_time-preproc_time
	draw = draw_time-predict_time
	total = read + preproc + pred + draw
	fps = 1 / total
	print("read: %.3f [s]; preproc: %.3f [s]; pred: %.3f [s]; draw: %.3f [s]; total: %.3f [s]; fps: %.2f [Hz]" % 
		(read, preproc, pred, draw, total, fps))

cap.release()
cv2.destroyAllWindows()