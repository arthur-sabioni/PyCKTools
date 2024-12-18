from pycktools.output_handler.output_handler import OutputHandler
from pycktools.parser.folder_parser import FolderParser
from pycktools.metrics.metrics import Metrics

class PyCKTools:

    @staticmethod
    def run(path: str, output_format: str= 'csv', prefix: str= '') -> None:

        fp = FolderParser(path)
        fp.parse_path()

        metrics = Metrics(fp.parser.classes)
        results_class, results_methods = metrics.calculate_all_metrics()

        OutputHandler.save_results(
            results_class, results_methods, 'results', output_format, prefix
        )

if __name__ == "__main__":

    path = 'F:\\CEFET\\TCC\\PyCKTools\\pycktools\\example' 
    PyCKTools.run(path, 'csv')