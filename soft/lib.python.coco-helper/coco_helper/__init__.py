#!/usr/bin/env python3

import os
import numpy as np


## Processing in batches:
#
BATCH_SIZE              = int(os.getenv('CK_BATCH_SIZE', 1))
BATCH_COUNT_SET         = os.getenv('CK_BATCH_COUNT', '') != ''
if BATCH_COUNT_SET:
    BATCH_COUNT         = int(os.getenv('CK_BATCH_COUNT', 1))
    SKIP_IMAGES         = int(os.getenv('CK_SKIP_IMAGES', 0))


## Model properties:
#
MODEL_IMAGE_HEIGHT      = int(os.getenv('ML_MODEL_IMAGE_HEIGHT',
                              os.getenv('CK_ENV_ONNX_MODEL_IMAGE_HEIGHT',
                              os.getenv('CK_ENV_TENSORFLOW_MODEL_IMAGE_HEIGHT',
                              ''))))
MODEL_IMAGE_WIDTH       = int(os.getenv('ML_MODEL_IMAGE_WIDTH',
                              os.getenv('CK_ENV_ONNX_MODEL_IMAGE_WIDTH',
                              os.getenv('CK_ENV_TENSORFLOW_MODEL_IMAGE_WIDTH',
                              ''))))
MODEL_IMAGE_CHANNELS    = int(os.getenv('ML_MODEL_IMAGE_CHANNELS', 3))
MODEL_DATA_LAYOUT       = os.getenv('ML_MODEL_DATA_LAYOUT', 'NCHW')
MODEL_COLOURS_BGR       = os.getenv('ML_MODEL_COLOUR_CHANNELS_BGR', 'NO') in ('YES', 'yes', 'ON', 'on', '1')
MODEL_INPUT_DATA_TYPE   = os.getenv('ML_MODEL_INPUT_DATA_TYPE', 'float32')
MODEL_DATA_TYPE         = os.getenv('ML_MODEL_DATA_TYPE', '(unknown)')
MODEL_USE_DLA           = os.getenv('ML_MODEL_USE_DLA', 'NO') in ('YES', 'yes', 'ON', 'on', '1')
MODEL_MAX_BATCH_SIZE    = int(os.getenv('ML_MODEL_MAX_BATCH_SIZE', BATCH_SIZE))
MODEL_SKIPPED_CLASSES   = os.getenv("ML_MODEL_SKIPS_ORIGINAL_DATASET_CLASSES", None)

if (MODEL_SKIPPED_CLASSES):
    SKIPPED_CLASSES = [int(x) for x in MODEL_SKIPPED_CLASSES.split(",")]
else:
    SKIPPED_CLASSES = None


## Internal processing:
#
INTERMEDIATE_DATA_TYPE  = np.float32    # default for internal conversion
#INTERMEDIATE_DATA_TYPE  = np.int8       # affects the accuracy a bit


## Image normalization:
#
MODEL_NORMALIZE_DATA    = os.getenv('ML_MODEL_NORMALIZE_DATA') in ('YES', 'yes', 'ON', 'on', '1')
MODEL_NORMALIZE_LOWER   = float(os.getenv('ML_MODEL_NORMALIZE_LOWER', -1.0))
MODEL_NORMALIZE_UPPER   = float(os.getenv('ML_MODEL_NORMALIZE_UPPER',  1.0))
SUBTRACT_MEAN           = os.getenv('ML_MODEL_SUBTRACT_MEAN', 'YES') in ('YES', 'yes', 'ON', 'on', '1')
GIVEN_CHANNEL_MEANS     = os.getenv('ML_MODEL_GIVEN_CHANNEL_MEANS', '')
if GIVEN_CHANNEL_MEANS:
    GIVEN_CHANNEL_MEANS = np.fromstring(GIVEN_CHANNEL_MEANS, dtype=np.float32, sep=' ').astype(INTERMEDIATE_DATA_TYPE)
    if MODEL_COLOURS_BGR:
        GIVEN_CHANNEL_MEANS = GIVEN_CHANNEL_MEANS[::-1]     # swapping Red and Blue colour channels

GIVEN_CHANNEL_STDS      = os.getenv('ML_MODEL_GIVEN_CHANNEL_STDS', '')
if GIVEN_CHANNEL_STDS:
    GIVEN_CHANNEL_STDS = np.fromstring(GIVEN_CHANNEL_STDS, dtype=np.float32, sep=' ').astype(INTERMEDIATE_DATA_TYPE)
    if MODEL_COLOURS_BGR:
        GIVEN_CHANNEL_STDS  = GIVEN_CHANNEL_STDS[::-1]      # swapping Red and Blue colour channels


## ImageNet dataset properties:
#
LABELS_PATH             = os.getenv('CK_ENV_TENSORRT_MODEL_FLATLABELS_FILE',
                            os.getenv('CK_ENV_ONNX_MODEL_FLATLABELS')
                            ) or os.environ['ML_MODEL_CLASS_LABELS']


## Preprocessed input images' properties:
#
IMAGE_DIR               = os.getenv('CK_ENV_DATASET_OBJ_DETECTION_PREPROCESSED_DIR')
IMAGE_LIST_FILE_NAME    = os.getenv('CK_ENV_DATASET_OBJ_DETECTION_PREPROCESSED_SUBSET_FOF')
IMAGE_LIST_FILE         = os.path.join(IMAGE_DIR, IMAGE_LIST_FILE_NAME)
IMAGE_DATA_TYPE         = os.getenv('CK_ENV_DATASET_OBJ_DETECTION_PREPROCESSED_DATA_TYPE', 'uint8')


def load_labels(labels_filepath):
    my_labels = []
    input_file = open(labels_filepath, 'r')
    for l in input_file:
        my_labels.append(l.strip())
    return my_labels

class_labels    = load_labels(LABELS_PATH)
num_classes     = len(class_labels)
bg_class_offset = 1
class_map       = None
if (SKIPPED_CLASSES):
    class_map = []
    for i in range(num_classes + bg_class_offset):
        if i not in SKIPPED_CLASSES:
            class_map.append(i)


# Load preprocessed image filenames:
with open(IMAGE_LIST_FILE, 'r') as f:
    image_list = [s.strip() for s in f]

# Trim the input list of preprocessed files:
if BATCH_COUNT_SET:
    image_list = image_list[SKIP_IMAGES: BATCH_COUNT * BATCH_SIZE + SKIP_IMAGES]

# Creating a local list of processed files and parsing it:
image_filenames = []
original_w_h    = []
with open(IMAGE_LIST_FILE_NAME, 'w') as f:
    for line in image_list:
        f.write('{}\n'.format(line))
        file_name, width, height = line.split(";")
        image_filenames.append( file_name )
        original_w_h.append( (int(width), int(height)) )


def load_image_by_index_and_normalize(image_index):
    img_file = os.path.join(IMAGE_DIR, image_filenames[image_index])
    img = np.fromfile(img_file, np.dtype(IMAGE_DATA_TYPE))
    img = img.reshape((MODEL_IMAGE_HEIGHT, MODEL_IMAGE_WIDTH, MODEL_IMAGE_CHANNELS))
    if MODEL_COLOURS_BGR:
        img = img[...,::-1]     # swapping Red and Blue colour channels

    if IMAGE_DATA_TYPE != 'float32':
        img = img.astype(np.float32)

        # Normalize
        if MODEL_NORMALIZE_DATA:
            img = img*(MODEL_NORMALIZE_UPPER-MODEL_NORMALIZE_LOWER)/255.0+MODEL_NORMALIZE_LOWER

        # Subtract mean value
        if SUBTRACT_MEAN:
            if len(GIVEN_CHANNEL_MEANS):
                img -= GIVEN_CHANNEL_MEANS
            else:
                img -= np.mean(img, axis=(0,1), keepdims=True)

        if len(GIVEN_CHANNEL_STDS):
            img /= GIVEN_CHANNEL_STDS

    if MODEL_INPUT_DATA_TYPE == 'int8' or INTERMEDIATE_DATA_TYPE==np.int8:
        img = np.clip(img, -128, 127).astype(INTERMEDIATE_DATA_TYPE)

    if MODEL_DATA_LAYOUT == 'NCHW':
        img = img.transpose(2,0,1)
    elif MODEL_DATA_LAYOUT == 'CHW4':
        img = np.pad(img, ((0,0), (0,0), (0,1)), 'constant')

    # Add img to batch
    return img.astype(MODEL_INPUT_DATA_TYPE)


def load_preprocessed_batch(image_list, image_index):
    batch_data = []
    for _ in range(BATCH_SIZE):
        img = load_image_by_index_and_normalize(image_index)

        batch_data.append( [img] )
        image_index += 1

    batch_data = np.concatenate(batch_data, axis=0)
    #print('Data shape: {}'.format(batch_data.shape))

    if MODEL_USE_DLA and MODEL_MAX_BATCH_SIZE>len(batch_data):
        return np.pad(batch_data, ((0,MODEL_MAX_BATCH_SIZE-len(batch_data)), (0,0), (0,0), (0,0)), 'constant'), image_index
    else:
        return batch_data, image_index

