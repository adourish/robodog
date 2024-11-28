import yaml from 'js-yaml';

import { YamlConfigService } from './YamlConfigService'
import { StorageService } from './StorageService'

const yamConfigService = new YamlConfigService();
const storageService = new StorageService();

class ProviderService {
  constructor() {
    console.debug('ProviderService init')
  }
  getDefaults(){
    var yamlstring = yamConfigService.getDefaults();
    return yamlstring;
  }

  setYaml(yaml, yamlkey = 'yaml') {
    console.debug('setYaml',yamlkey, yaml)
    storageService.setItem(yamlkey, yaml);
  }

  getYaml(yamlkey = 'yaml') {
    const yamlstring = storageService.getItem(yamlkey);
    console.debug('getYaml', yamlkey, yaml)
    if (yamlstring) {
      return yamlstring;
    } else {
      return this.getDefaults();
    }
  }

  getCurrentModel() {
    const modelName = storageService.getItem('model');
    console.debug('model', modelName)
    return modelName;
  }
  setCurrentModel(modelName) {
    console.debug('Set model', modelName)
    storageService.setItem('model', modelName);
  }
  getSpecialist(specialistName){
    var model = null;
    var config = this.getJson();
    if(config.configs && config.configs.specialists){
      var specialists = config.configs.specialists;
      for (var i = 0; i < specialists.length; i++) {
        if (specialists[i].model === specialistName) {
          specialists = specialists[i];
          break;
        }
      }
    }
    return specialists;
  }

  getModel(modelName){
    var model = null;
    var config = this.getJson();
    if(config.configs && config.configs.models){
      var models = config.configs.models;
      for (var i = 0; i < models.length; i++) {
        if (models[i].model === modelName) {
          model = models[i];
          break;
        }
      }
    }
    return model;
  }

  reset(yamlkey = 'yaml'){
    storageService.removeItem('openaiAPIKey');
    storageService.removeItem(yamlkey);
    storageService.removeItem('rapidapiAPIKey');
  }
  getModels(){
    var config = this.getJson();
    if(config.configs && config.configs.models){
      return config.configs.models;
    }
  }
  getProvider(providerName){
    var provider = null;
    var config = this.getJson();
    if(config.configs && config.configs.providers){
      var providers = config.configs.providers;
      for (var i = 0; i < providers.length; i++) {
        if (providers[i].provider === providerName) {
          provider = providers[i];
          break;
        }
      }
    }
    return provider;
  }

  getJson() {
    const yamlContent = this.getYaml();
    console.log('yamlContent', yamlContent);
    try {
      // Convert YAML content to JSON using a library like js-yaml
      const jsonContent = yaml.load(yamlContent);
      return jsonContent;
    } catch (error) {
      console.error('Error converting YAML to JSON:', error);
      return null;
    }
  }

}

export  { ProviderService };