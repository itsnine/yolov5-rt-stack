# Ncnn Inference

The ncnn inference for `yolort`, both GPU and CPU are supported.

## Dependencies

- Ubuntu 18.04
- ncnn
- OpenCV 3.4+

## Usage

1. First, Setup the environment variables.

    ```bash
    export TORCH_PATH=$(dirname $(python -c "import torch; print(torch.__file__)"))
    export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$TORCH_PATH/lib/
    ```

1. First, compile `ncnn` using the following scripts.

    ```bash
    git clone --recursive git@github.com:Tencent/ncnn.git
    cd ncnn
    mkdir build && cd build
    cmake -DCMAKE_BUILD_TYPE=Release -DNCNN_SYSTEM_GLSLANG=ON -DNCNN_BUILD_EXAMPLES=ON .. # Set -DNCNN_VULKAN=ON if you're using VULKAN
    make -j4
    make install
    ```

    Or follow the [official instructions](https://github.com/Tencent/ncnn/wiki/how-to-build) to install ncnn.

1. Then compile the source code.

    ```bash
    cd deployment/ncnn
    mkdir build && cd build
    cmake .. -Dncnn_DIR=<ncnn_install_dir>/lib/cmake/ncnn/
    make
    ```

_Note: you have to change <ncnn_install_dir> to your machine's directory, it is the directory that contains ncnnConfig.cmake, if you are following the above operations, you should set it to <./ncnn/build/install>_

1. Now, you can infer your own images with ncnn.

    ```bash
    ./yolort_ncnn ../../../test/assets/zidane.jpg
    ```
