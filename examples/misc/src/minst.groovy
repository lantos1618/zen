




main: Function {
    args: {},
    return: {},
    body: {
        // read minst data
        trainImages: Array {Array {Int.i32}}
        trainLabels: Array {Int.i32}

        testImages: Array {Array {Int.i32}}
        testLabels: Array {Int.i32}

        // read train data
        trainFileImages: File("examples/misc/data/train-images-idx3-ubyte")
        trainFileImages.readBytes(trainImages.ref(), 16, 28 * 28)
        trainFileImages.close()

        trainFileLabels: File("examples/misc/data/train-labels-idx1-ubyte")
        trainFileLabels.readBytes(trainLabels.ref(), 8, 1)
        trainFileLabels.close()

        // read test data
        testFileImages: File("examples/misc/data/t10k-images-idx3-ubyte")
        testFileImages.readBytes(testImages.ref(), 16, 28 * 28)
        testFileImages.close()

        testFileLabels: File("examples/misc/data/t10k-labels-idx1-ubyte")
        testFileLabels.readBytes(testLabels.ref(), 8, 1)
        testFileLabels.close()

        // create network
        MinstNet:  Type {
            self: Network
            layers: {
                conv1: Convolutional2d(
                    inputChannels: 1,
                    outputChannels: 32,
                    kernelSize: 5,
                    stride: 1,
                    padding: 2
                ),
                conv2: Convolutional2d(
                    inputChannels: 32,
                    outputChannels: 64,
                    kernelSize: 5,
                    stride: 1,
                    padding: 2
                ),
                dropOut1: Dropout(
                    probability: 0.25
                ),
                dropOut2: Dropout(
                    probability: 0.5
                ),
                fc1: FullyConnected(
                    inputSize: 7 * 7 * 64,
                    outputSize: 1024
                ),
                fc2: FullyConnected(
                    inputSize: 1024,
                    outputSize: 10
                )
            }
            forward: {
                args: {
                    self: MinstNet,
                    input: Array {Array {Int.i32}},
                },
                return: {
                    output: Array {Int.i32}
                },
                body: {
                    // input is 28x28
                    // conv1 is 28x28x32
                    // conv2 is 28x28x64
                    // maxPool1 is 14x14x64
                    // maxPool2 is 7x7x64
                    // fc1 is 1024
                    // fc2 is 10
                    layers.conv1.forward(args.input, output)
                    layers.maxPool1.forward(output, output)
                    layers.conv2.forward(output, output)
                    layers.maxPool2.forward(output, output)
                    layers.dropOut1.forward(output, output)
                    layers.fc1.forward(output, output)
                    layers.dropOut2.forward(output, outpot)
                    layers.fc2.forward(outpot, output)
                    retrun(output)
                }

            }
        }
        model: MinstNet()
        optim: Optimizer.Adam(model.parameters(), 0.001)
        loss: Loss.NLL()

        // train
        epochs: Int(10)
        batchSize: Int(64)
        trainLoop: Loop(epochs) {
            batchLoop: Loop(trainImages.size() / batchSize ) {
                optim.zeroGrad()
                batch: Array {Array {Int.i32}}
                batchLabels: Array {Int.i32}
                batchImages: Array {Array {Int.i32}}
                batchLabels: Array {Int.i32}
                trainImages.slice(batchLoop.value * batchSize, batchSize, batchImages.ref())
                trainLabels.slice(batchLoop.value * batchSize, batchSize, batchLabels.ref())
                batchImages.map(batchImages.ref(), batch.ref(), {
                    image: Array {Int.i32}
                    image: Array {Float}
                    image.map(image.ref(), image.ref(), {
                        pixel: Int.i32
                        pixel: Float
                        pixel / 255.0
                    })
                    image
                })
                output: Array {Int.i32}
                model.forward(batch, output)
                lossValue: Float
                loss.forward(output, batchLabels, lossValue.ref())
                loss.backward()
                optim.step()
                print("Epoch: ", trainLoop.value, " Batch: ", batchLoop.value, " Loss: ", lossValue)
            }
        }

        // test
        correct: Int(0)
        testLoop: Loop(testImages.size()) {
            image: Array {Int.i32}
            image: Array {Float}
            testImages[testLoop.value].map(image.ref(), image.ref(), {
                pixel: Int.i32
                pixel: Float
                pixel / 255.0
            })
            output: Array {Int.i32}
            model.forward(image, output)
            prediction: Int.i32
            output.max(prediction.ref())
            if (prediction == testLabels[testLoop.value]) {
                correct.increment()
            }
        }

        print("Accuracy: ", correct / testImages.size())

    }
}