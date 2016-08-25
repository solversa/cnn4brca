# Written by: Erick Cobos T. (a01184587@itesm.mx)
# Date: April 2016
""" Calculate evaluation metrics for different thresholds (for cross-validation)

	We use linearly spaced probabilities in the range between the smallest and 
	largest possible predicted probability (as estimated by the predictions on 
	a random example). Thresholds are the logits corresponding to these
	probabilities.
	
	Example:
		$ python3 val.py
		$ python3 val.py | tee eval
"""

import tensorflow as tf
import model_v3 as model
import csv
import scipy.misc
import numpy as np

checkpoint_dir = "checkpoint"
csv_path = "val/val.csv"
data_dir = "val/"
number_of_thresholds = 25

def post(logits, label, threshold):
	"""Creates segmentation assigning everything over the threshold a value of 
	255, anythig equals to background in label as 0 and anythign else 127. 
	
	Using the label may seem like cheating but the background part of the label 
	was generated by thresholding the original image to zero, so it is as if i
	did that here. Just that it is more cumbersome. Not that important either as
	I calculate IOU for massses and not for backgorund or breats tissue."""
	thresholded = np.ones(logits.shape, dtype='uint8') * 127
	thresholded[logits >= threshold] = 255
	thresholded[label == 0] = 0
	return thresholded
	
def compute_confusion_matrix(segmentation, label):
	"""Confusion matrix for a mammogram: # of pixels in each category."""
	# Confusion matrix (only over breast area)
	true_positive = np.sum(np.logical_and(segmentation == 255, label == 255))
	false_positive = np.sum(np.logical_and(segmentation == 255, label != 255))
	true_negative = np.sum(np.logical_and(segmentation == 127, label == 127))
	false_negative = np.sum(np.logical_and(segmentation == 127, label != 127))
	
	cm_values = [true_positive, false_positive, true_negative, false_negative]
	
	return np.array(cm_values)
	
def compute_metrics(true_positive, false_positive, true_negative, false_negative):
	"""Array with different metrics from the given confusion matrix values."""
	epsilon = 1e-7 # To avoid division by zero
	
	# Evaluation metrics
	accuracy = (true_positive + true_negative) / (true_positive + true_negative 
									+ false_positive + false_negative + epsilon)
	sensitivity = true_positive / (true_positive + false_negative + epsilon)
	specificity = true_negative / (false_positive + true_negative + epsilon)
	precision = true_positive / (true_positive + false_positive + epsilon)
	recall = sensitivity
	iou = true_positive / (true_positive + false_positive + false_negative + 
						   epsilon)
	f1 = (2 * precision * recall) / (precision + recall + epsilon)
	g_mean = np.sqrt(sensitivity * specificity)
		
	metrics = [iou, f1, g_mean, accuracy, sensitivity, specificity, precision,
			   recall]

	return np.array(metrics)
	
def main():
	""" Loads network, reads image and returns mean metrics."""
	# Read csv file
	with open(csv_path) as f:
		lines = f.read().splitlines()
		
	# Image as placeholder.
	image = tf.placeholder(tf.float32, name='image')
	expanded = tf.expand_dims(image, 2)
	whitened = tf.image.per_image_whitening(expanded)
	
	# Define the model
	prediction = model.model(whitened, drop=tf.constant(False))
		
	# Get a saver
	saver = tf.train.Saver()

	# Use CPU-only. To enable GPU, delete this and call with tf.Session() as ...
	config = tf.ConfigProto(device_count={'GPU':0})
	
	# Launch graph
	with tf.Session(config=config) as sess:
		# Restore variables
		checkpoint_path = tf.train.latest_checkpoint(checkpoint_dir)
		saver.restore(sess, checkpoint_path)
		model.log("Variables restored from:", checkpoint_path)
		
		# Get random probs in 10^unif(-3, 0) range
		#probs = 10 ** np.random.uniform(-3, 0, number_of_thresholds)
		
		# Get probabilities uniformly distributed between zero and 1
		probs = np.linspace(0.001, 0.999, number_of_thresholds)
		
		# Get random probabilities estimated from an example
		"""
		rand_index = np.random.randint(len(lines))
		rand_line = lines[rand_index]
		for row in csv.reader([rand_line]): 
			# Read image
			image_path = data_dir + row[0]
			im = scipy.misc.imread(image_path)
		
			# Get prediction
			logits = prediction.eval({image: im})
			
			# Minimum and maximum predicted probability
			min_prob = 1/ (1 + np.exp(-logits.min()))
			max_prob = 1/ (1 + np.exp(-logits.max()))
			
			# Get thresholds in (min_prob, max_prob) range
			probs = np.linspace(min_prob, max_prob, number_of_thresholds)
		"""	
		# Transform probabilities to logits (thresholds)
		thresholds = np.log(probs) - np.log(1 - probs) #prob2logit
		
		# Validate each threshold
		for i in range(number_of_thresholds):
			print("Threshold {}: {} ({})".format(i, thresholds[i], probs[i]))
			
			# Reset reader and metric_accum
			csv_reader = csv.reader(lines)
			confusion_matrix = np.zeros(4) # tp, fp, tn, fn
			confusion_matrix2 = np.zeros(4) # tp, fp, tn, fn
			
			# For every example
			for row in csv_reader:
				# Read paths
				image_path = data_dir + row[0]
				label_path = data_dir + row[1]

				# Read image and label
				im = scipy.misc.imread(image_path)
				label = scipy.misc.imread(label_path)
			
				# Get prediction
				logits = prediction.eval({image: im})
			
				# Post-process prediction
				segmentation = post(logits, label, thresholds[i])
				
				# Accumulate confusion matrix values
				confusion_matrix += compute_confusion_matrix(segmentation, label)
				if label.max() == 255: # only if the mammogram had a mass
					confusion_matrix2 += compute_confusion_matrix(segmentation, label)
						
			# Calculate metrics
			metrics = compute_metrics(*confusion_matrix)
			metrics2 = compute_metrics(*confusion_matrix2)
			
			# Report metrics
			metric_names = ['IOU', 'F1-score', 'G-mean', 'Accuracy',
						   'Sensitivity', 'Specificity', 'Precision', 'Recall']
			for name, metric, metric2 in zip(metric_names, metrics, metrics2):
				print("{}: {} / {}".format(name, metric, metric2))
			print('')
				
		# Logistic loss (same for any threshold)
		label = tf.placeholder(tf.uint8, name='label')
		loss = model.logistic_loss(prediction, label)
		
		csv_reader = csv.reader(lines)
		loss_accum = 0
		for row in csv_reader:
			im = scipy.misc.imread(data_dir + row[0])
			lbl = scipy.misc.imread(data_dir + row[1])
			
			loss_accum += loss.eval({image:im, label:lbl})
			
		print("Logistic loss: ", loss_accum/csv_reader.line_num)
				
	return metrics, metric_names
	
if __name__ == "__main__":
	main()
