import tensorflow as tf
import numpy as np
import os
from tfcone.inout import dennerlein, projtable
from tfcone.algo import ct
from tensorflow.python.client import timeline

# CONFIG
#-------------------------------------------------------------------------------------------
DATA_P = os.path.abspath(
        os.path.dirname( os.path.abspath( __file__ ) ) + '/../phantoms/conrad-2/'
    ) + '/'

RAMLAK_WIDTH = 101
VOLUME_SHAPE = [ 200, 200, 200 ]
VOLUME_ORIGIN = [ -99.5, -99.5, -99.5 ]
PIXEL_WIDTH_MM = 1
PIXEL_HEIGHT_MM = 1
SOURCE_DET_DISTANCE = 1200
N = 200
U = 620
V = 480


# GLOBALS
#-------------------------------------------------------------------------------------------
asserts = []


# READ DATA
#-------------------------------------------------------------------------------------------
proj = dennerlein.read( DATA_P + 'shepp-logan-proj.bin' )
geom, angles = projtable.read( DATA_P + 'projMat.txt' )
geom_tensor = tf.constant( geom, dtype = tf.float32 )
proj_shape = tf.shape( proj )
with tf.control_dependencies( [ proj ] ):
    asserts.append( tf.assert_equal( tf.shape( proj ), [ N, V, U ] ) )


# COSINE
#-------------------------------------------------------------------------------------------
cosine_w_np = ct.init_cosine_3D( SOURCE_DET_DISTANCE, U, V, PIXEL_WIDTH_MM,
        PIXEL_HEIGHT_MM )
cosine_w = tf.constant( cosine_w_np, dtype = tf.float32 )
proj_cosine = tf.multiply( proj, cosine_w )


# PARKER
#-------------------------------------------------------------------------------------------
parker_w_np = ct.init_parker_3D( angles, SOURCE_DET_DISTANCE, U, PIXEL_WIDTH_MM )
parker_w = tf.constant( parker_w_np, dtype = tf.float32 )
proj_parker = tf.multiply( proj_cosine, parker_w )


# RAMLAK
#-------------------------------------------------------------------------------------------

# TODO: Seems like cudnn does not support 3D convolutions.. Find a way to do
# that with conv2d..

# need format batch, depth, height, width, channel for conv3d
proj_batch = tf.reshape( proj_parker, [ 1, N, V, U, 1 ] )

def kernel_init( shape, dtype, partition_info = None ):
    kernel = tf.Variable( ct.init_ramlak_1D( RAMLAK_WIDTH, PIXEL_WIDTH_MM ), dtype = dtype )
    return tf.reshape( kernel, shape )

ramlak_batch = tf.layers.conv3d(
        inputs = proj_batch,
        filters = 1,
        kernel_size = [ 1, 1, RAMLAK_WIDTH ],
        padding = 'same',
        use_bias = False,
        kernel_initializer = kernel_init,
        name = 'ramlak-filter'
    )
proj_ramlak = tf.reshape( ramlak_batch, [ N, V, U ] )


# BACKPROJECTION
#-------------------------------------------------------------------------------------------
vo = tf.contrib.util.make_tensor_proto( VOLUME_ORIGIN,
        tf.float32 )
volume = ct.backproject(
        projections = proj_ramlak,
        geom = geom_tensor,
        vol_shape = VOLUME_SHAPE,
        vol_origin=vo
    )


# WRITE RESULT
#-------------------------------------------------------------------------------------------
write_op = dennerlein.write( '/tmp/test-cos.bin', volume )


with tf.Session() as sess:
    sess.run( tf.global_variables_initializer() )

    # tracing according to http://stackoverflow.com/questions/34293714/can-i-measure-the-execution-time-of-individual-operations-with-tensorflow
    run_options = tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE)
    run_metadata = tf.RunMetadata()

    v = sess.run( [ write_op ] + asserts, options = run_options, run_metadata = run_metadata )

    # write timeline object to file
    tl = timeline.Timeline(run_metadata.step_stats)
    ctf = tl.generate_chrome_trace_format()
    with open('timeline.json', 'w') as f:
        f.write(ctf)


