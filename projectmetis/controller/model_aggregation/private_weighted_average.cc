// MIT License
//
// Copyright (c) 2021 Project Metis
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

#include "projectmetis/controller/model_aggregation/private_weighted_average.h"

#include "projectmetis/proto/model.pb.h"

namespace projectmetis::controller {

FederatedModel
PWA::Aggregate(
    std::vector<std::pair<const Model*, double>>& pairs) {

  std::vector<float> scalingFactors;
  for (const auto &pair : pairs) {
    const auto scale = (float) pair.second;
    scalingFactors.emplace_back(scale);
  }

  // Initializes the community model.
  FederatedModel community_model;
  const auto& sample_model = pairs.front().first;
  // Loop over each variable one-by-one.
  for (int i = 0; i < sample_model->variables_size(); ++i) {
    auto* variable = community_model.mutable_model()->add_variables();
    variable->set_name(sample_model->variables(i).name());
    variable->set_trainable(sample_model->variables(i).trainable());
    *variable->mutable_ciphertext_tensor()->mutable_spec() =
        sample_model->variables(i).ciphertext_tensor().spec();

    std::vector<std::string> learners_Data;
    for (const auto &pair : pairs) {
      const auto *model = pair.first;
      learners_Data.emplace_back(
          model->variables(i).ciphertext_tensor().values());
    }
    std::string pwa_result =
        fhe_helper_.computeWeightedAverage(learners_Data, scalingFactors);
    *variable->mutable_ciphertext_tensor()->mutable_values() = pwa_result;
  }

  // Sets the number of contributors to the number of input models.
  community_model.set_num_contributors(pairs.size());
  return community_model;
}

} // namespace projectmetis::controller
