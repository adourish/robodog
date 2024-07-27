import yaml from 'js-yaml';

import { YamlConfigService } from './YamlConfigService'
const yamConfigService = new YamlConfigService();
class ProviderService {
  constructor() {
    console.debug('ProviderService init')
  }
  getDefaults(){
    var yamlstring = yamConfigService.getDefaults();
    return yamlstring;
  }

  setYaml(yaml) {
    console.debug('Set yaml', yaml)
    localStorage.setItem('yaml', yaml);
  }

  getYaml() {
    const yamlstring = localStorage.getItem('yaml');
    console.debug('yaml', yaml)
    if (yamlstring) {
      return yamlstring;
    } else {
      return this.getDefaults();
    }
  }

  getCurrentModel() {
    const modelName = localStorage.getItem('model');
    console.debug('model', modelName)
    return modelName;
  }
  setCurrentModel(modelName) {
    console.debug('Set model', modelName)
    localStorage.setItem('model', modelName);
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

  reset(){
    localStorage.removeItem('openaiAPIKey');
    localStorage.removeItem('yaml');
    localStorage.removeItem('rapidapiAPIKey');
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