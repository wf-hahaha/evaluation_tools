#!/usr/bin/env python3

import re
import os
import sys
import time
import yaml
import logging
import tarfile
#import urllib.request
import urllib
import hashlib
import argparse
import catkin_utils
import IPython
import shutil

def getDatasetList():
    logger = logging.getLogger(__name__)
    datasets_yaml = getLocalDatasetsFolder() + '/datasets.yaml'

    if os.path.exists(datasets_yaml):
        dataset_list = yaml.load(open(datasets_yaml,'r'))
       
        # Create dictonary of datasets and check if they are well formatted.
        datasets = dict()
        for dataset in dataset_list:
            if "name" not in dataset:
                logger.warning("Malformed dataset entry: 'name' key not found")
                continue
            if "dir" not in dataset:
                logger.warning("Malformed dataset entry: no 'dir' tag found.")
                continue
            datasets[dataset["name"]] = dataset           
        return datasets
    raise ValueError("Could not find 'datasets.yaml' in evaluation package.")

def getLocalDatasetsFolder():  
  evaluation_folder = catkin_utils.catkinFindSrc("evaluation_tools")
  return evaluation_folder + '/datasets'
    
def getDownloadedDatasets():
    local_datasets_dir = getLocalDatasetsFolder()
    downloaded_datasets = [name for name in os.listdir(local_datasets_dir) if re.search('.*.yaml', name) is None]
    return downloaded_datasets, local_datasets_dir  

def listDatasets():
    all_datasets = getDatasetList()
    downloaded_datasets, data_dir = getDownloadedDatasets()
    
    row_format = "{:<30} {:<15} {:<15}"
    print(row_format.format("Dataset Name", "Downloaded", "Version"))
    print(row_format.format("------------", "----------", "-------"))
    for dataset_name, dataset in sorted(all_datasets.items()):
        downloaded = False
        hash_status = " "
        if dataset_name in downloaded_datasets:
            downloaded = True
            
            # Check if hash is ok:
            hash_status = "No version file"
            if 'sha1' in dataset:
                version_filename = os.path.join(data_dir, dataset_name, "version.sha1")
                if os.path.exists(version_filename):
                    with open(version_filename, 'r') as afile:
                        version = afile.read().replace('\n', '')
                    hash_status = "OK" if dataset['sha1'] == version else "Old Version"
            if 'version' in dataset:
                version_filename = os.path.join(data_dir, dataset_name, "version.txt")
                if os.path.exists(version_filename):
                    with open(version_filename, 'r') as afile:
                        version = afile.read().replace('\n', '')
                    hash_status = "OK" if str(dataset['version']) == str(version) else "Old Version"
            
        print(row_format.format(dataset_name, "Yes" if downloaded else "No", hash_status))
        
def _download_reporthook(count, block_size, total_size):
    global start_time
    if count == 0:
        start_time = time.time()
        return
    duration = time.time() - start_time
    progress_size = int(count * block_size)
    speed = int(progress_size / (1024 * duration))
    percent = int(count * block_size * 100 / total_size)
    sys.stdout.write("\r...%d%%, %d MB, %d KB/s, %d seconds passed" %
                    (percent, progress_size / (1024 * 1024), speed, duration))
    sys.stdout.flush()
           
def downloadFileFromServer(file_url, local_filename):
    logger = logging.getLogger(__name__)  
    logger.info('Downloading file from server from {0}'.format(file_url))
    logger.info('to {0}'.format(local_filename))
    urllib.request.urlretrieve(file_url, local_filename, _download_reporthook)
    logger.info('\ndone.')
    assert os.path.exists(local_filename) #TODO(cfo): checksum    
    
def validFileOnServer(filename):
    logger = logging.getLogger(__name__)  
    try:
        urllib.request.urlopen(filename)
    except urllib.error.URLError as err:
        logger.warning('We failed to load URL. Reason: {0}'.format(err.reason))
        return False
    except ValueError as err:
        logger.warning('Unknown URL type: {0}'.format(filename))
        return False
    return True
    
def extractListOfFilesFromOnlineDirectoryListing(url):
    webpage = urllib.request.urlopen(url).read().decode('ascii')
    links = re.findall('<a href="(.+?)">', webpage)
    # no links with '/' to avoid downloading a subfolder
    filenames = [link for link in links if '/' not in link] 
    return filenames
    
def getFileHash(filename):
    logger = logging.getLogger(__name__)    
    logger.debug("Creating hash of file: " + filename)
    if not os.path.exists(filename):
        raise ValueError("File does not exist: "+filename)
    file_hash = hashlib.sha1(open(filename, 'rb').read()).hexdigest()
    return file_hash

def downloadDataset(dataset_name, replace = False):
    logger = logging.getLogger(__name__)
        
    # Check that dataset_name is valid:
    datasets = getDatasetList()
    if dataset_name not in datasets:
        logger.warning("Dataset: "+dataset_name+" is not valid. Check datasets.yaml"
                       " for available datasets.")
        return
    dataset = datasets[dataset_name]
    
    # Create target directory:
    local_data_dir = getLocalDatasetsFolder()
    #dataset_dir = os.path.join(data_dir, dataset['name'])    
    #if os.path.exists(dataset_dir):
    #    logger.warning("Dataset folder already exists: "+dataset_dir)
    #    if not replace:
    #        return
    #    else:
    #        logger.info("Delete old dataset folder: "+dataset_dir)
    #        os.system("rm -rf " + dataset_dir)
    
    #logger.info("Creating dataset folder: "+dataset_dir)
    #os.makedirs(dataset_dir)
    
    
    # -------------------------------------------------------------------------
    # Download zip from url
    if 'url' in dataset:    
      # Download dataset files from server as specified in info YAML.
      url = dataset['url'].replace('ZE_DATASET_SERVER', ZE_DATASET_SERVER)
      filename = url.split('/')[-1]    
      local_filename = os.path.join(dataset_dir, filename)
      if validFileOnServer(url):
          downloadFileFromServer(url, local_filename)
      else:
          logger.warning('File {0} does not exist on server.'.format(url))
  
      # compute a hash of the file
      downloaded_file_hash = getFileHash(local_filename)
      version_file = open(os.path.join(dataset_dir, 'version.sha1'), 'w')
      version_file.write('{0}'.format(downloaded_file_hash)) 
      version_file.close()
      
      # check if hash is ok and write it 
      if 'sha1' in dataset:
          if downloaded_file_hash == dataset['sha1']:
              logger.info("Successfully verified hash-key of downloaded file")
          else:
              raise ValueError("Hash of downloaded dataset is not valid: "+filename)
          
      # unpack tar.gz
      if local_filename.split(".")[-2] == 'tar' and local_filename.split(".")[-1] == 'gz':
          logger.info("Unpacking .tar.gz file...")
          tfile = tarfile.open(local_filename, 'r:gz')
          tfile.extractall(dataset_dir)
          logger.info("...done.")

    # -------------------------------------------------------------------------
    # Download a whole directory          
    elif 'webdir' in dataset:
      webdir = dataset['webdir'].replace("ZE_DATASET_SERVER", ZE_DATASET_SERVER)
      filenames = extractListOfFilesFromOnlineDirectoryListing(webdir)
      for filename in filenames:
          url = os.path.join(webdir, filename)
          local_filename = os.path.join(dataset_dir, filename)
          downloadFileFromServer(url, local_filename)            
          
      # Save a version file in the directory
      if 'version' in dataset:
          logger.info("Write version '"+str(dataset['version'])+"' to file.")
          version_file = open(os.path.join(dataset_dir, 'version.txt'), 'w')
          version_file.write('{0}'.format(str(dataset['version']))) 
          version_file.close()
            
    elif 'dir' in dataset:
      print ('Starting copying of dataset to local folder...')
      shutil.copyfile(dataset['dir'] + '/' + dataset['name'], local_data_dir + '/' + dataset['name'])
      print ('Done.')
    else:
      raise Exception("Unclear how to download the dataset.")
           
if __name__ == '__main__':
    usage = """
        List and download available Zurich-Eye datasets.
    """
    parser = argparse.ArgumentParser(description=usage)
    parser.add_argument('--list', dest='list_datasets', action='store_true',
                        help='List all available datasets"')
                        
    parser.add_argument('--fetch', dest='fetch_dataset', default='',
                        help='Download dataset')
                        
    parser.add_argument('--f', dest='force', action='store_true',
                        help='Force downloading dataset.')
                        
    parser.add_argument('--hash', dest='hash', default='',
                        help='Create hash of file.')
                        
    # Parse command-line arguments
    options = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    
    if options.list_datasets:
        list_datasets()
      
    if options.fetch_dataset:
        downloadDataset(options.fetch_dataset, options.force)
        
    if options.hash:
        file_hash = getFileHash(options.hash)
        print(file_hash)
        
